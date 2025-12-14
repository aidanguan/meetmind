from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from models import Project, Recording, RecordingStatus, Transcript, MeetingMinutes
from pydantic import BaseModel
from typing import List, Optional
import shutil
import os
import uuid
import datetime
from tasks import transcribe_audio, generate_minutes
import redis
from services.llm import LLMService

router = APIRouter(prefix="/recordings", tags=["recordings"])

UPLOAD_DIR = "/app/media"  # Mapped volume path

def to_media_url(file_path: str) -> str:
    if not file_path:
        return ""
    # Map container file path to static mount
    # /app/media/uuid.ext -> /media/uuid.ext
    if file_path.startswith("/app/media"):
        return file_path.replace("/app", "")
    return file_path

class RecordingOut(BaseModel):
    id: int
    project_id: int
    filename: str
    status: RecordingStatus
    duration: Optional[int]
    created_at: Optional[object] # datetime

    class Config:
        orm_mode = True

class TranscriptOut(BaseModel):
    id: int
    content: List[dict]
    plain_text: str

    class Config:
        orm_mode = True

class MinutesOut(BaseModel):
    id: int
    content: str
    
    class Config:
        orm_mode = True
 
class RecordingDetailOut(BaseModel):
    id: int
    project_id: int
    project_name: str
    filename: str
    status: RecordingStatus
    duration: Optional[int]
    created_at: Optional[object]
    media_url: Optional[str]
    error_message: Optional[str] = None

    class Config:
        orm_mode = True

import subprocess

@router.post("/upload/{project_id}", response_model=RecordingOut)
def upload_recording(project_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)

    file_ext = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Calculate duration using ffprobe
    duration = 0
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        if result.returncode == 0:
            duration = float(result.stdout.strip())
    except Exception as e:
        print(f"Error calculating duration: {e}")

    db_recording = Recording(
        project_id=project_id,
        filename=file.filename,
        file_path=file_path,
        duration=int(duration), # Store as seconds
        status=RecordingStatus.PENDING
    )
    db.add(db_recording)
    db.commit()
    db.refresh(db_recording)
    return db_recording

@router.get("/project/{project_id}", response_model=List[RecordingOut])
def list_recordings(project_id: int, db: Session = Depends(get_db)):
    return db.query(Recording).filter(Recording.project_id == project_id).order_by(Recording.created_at.desc()).all()

@router.get("/{recording_id}", response_model=RecordingDetailOut)
def get_recording(recording_id: int, db: Session = Depends(get_db)):
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    err_msg = None
    if recording.status == RecordingStatus.ERROR:
        try:
            r = redis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                db=int(os.getenv("REDIS_DB", "0")),
                decode_responses=True
            )
            err_msg = r.get(f"recording_error:{recording.id}")
        except Exception as _:
            err_msg = None
    return {
        "id": recording.id,
        "project_id": recording.project_id,
        "project_name": recording.project.name if recording.project else "Unknown Project",
        "filename": recording.filename,
        "status": recording.status,
        "duration": recording.duration,
        "created_at": recording.created_at,
        "media_url": to_media_url(recording.file_path),
        "error_message": err_msg
    }

@router.post("/{recording_id}/transcribe")
def start_transcription(recording_id: int, db: Session = Depends(get_db)):
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    transcribe_audio.delay(recording_id)
    return {"message": "Transcription started"}

@router.get("/{recording_id}/transcript", response_model=TranscriptOut)
def get_transcript(recording_id: int, db: Session = Depends(get_db)):
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    if recording.status == RecordingStatus.ERROR:
        # fetch detailed error if any
        err_msg = None
        try:
            r = redis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                db=int(os.getenv("REDIS_DB", "0")),
                decode_responses=True
            )
            err_msg = r.get(f"recording_error:{recording.id}")
        except Exception as _:
            err_msg = None
        detail = "Transcription failed" + (f": {err_msg}" if err_msg else "")
        raise HTTPException(status_code=404, detail=detail)
    transcript = db.query(Transcript).filter(Transcript.recording_id == recording_id).first()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not ready")
    return transcript

class MinutesRequest(BaseModel):
    context: str = ""

@router.get("/{recording_id}/minutes/stream")
def stream_minutes(recording_id: int, context: str = "", db: Session = Depends(get_db)):
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    if not recording.transcript:
        raise HTTPException(status_code=400, detail="Transcript not ready")

    llm_service = LLMService()
    transcript_text = recording.transcript.plain_text
    
    # Prepend title and time to context if not already there
    meta_context = f"Title: {recording.filename}, Date: {recording.created_at}"
    full_context = f"{meta_context}. {context}"

    async def generate_and_save():
        full_content = ""
        stream = llm_service.stream_minutes_generator(transcript_text, full_context)
        for chunk in stream:
            full_content += chunk
            yield chunk
        
        # Save to DB after streaming is complete
        # Create a new session since the outer one might be closed or not thread-safe in async generator
        try:
            new_db = SessionLocal()
            minutes = new_db.query(MeetingMinutes).filter(MeetingMinutes.recording_id == recording_id).first()
            if minutes:
                minutes.content = full_content
            else:
                minutes = MeetingMinutes(
                    recording_id=recording_id,
                    content=full_content
                )
                new_db.add(minutes)
            new_db.commit()
            new_db.close()
        except Exception as e:
            print(f"Error saving minutes to DB: {e}")

    return StreamingResponse(generate_and_save(), media_type="text/plain")

@router.post("/{recording_id}/minutes")
def create_minutes(recording_id: int, request: MinutesRequest, db: Session = Depends(get_db)):
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    generate_minutes.delay(recording_id, request.context)
    return {"message": "Minutes generation started"}

@router.get("/{recording_id}/minutes", response_model=MinutesOut)
def get_minutes(recording_id: int, db: Session = Depends(get_db)):
    minutes = db.query(MeetingMinutes).filter(MeetingMinutes.recording_id == recording_id).first()
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    return minutes

class UpdateMinutesRequest(BaseModel):
    content: str

@router.put("/{recording_id}/minutes", response_model=MinutesOut)
def update_minutes(recording_id: int, request: UpdateMinutesRequest, db: Session = Depends(get_db)):
    minutes = db.query(MeetingMinutes).filter(MeetingMinutes.recording_id == recording_id).first()
    if not minutes:
         # Optionally create if not exists, but for now strict update
        raise HTTPException(status_code=404, detail="Minutes not found")
    
    minutes.content = request.content
    db.commit()
    db.refresh(minutes)
    return minutes

class UpdateSpeakerRequest(BaseModel):
    original_speaker_id: str
    new_speaker_id: str

class UpdateRecordingRequest(BaseModel):
    filename: Optional[str] = None
    created_at: Optional[datetime.datetime] = None

@router.put("/{recording_id}", response_model=RecordingOut)
def update_recording(recording_id: int, request: UpdateRecordingRequest, db: Session = Depends(get_db)):
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    if request.filename:
        recording.filename = request.filename
    
    if request.created_at:
        recording.created_at = request.created_at

    db.commit()
    db.refresh(recording)
    return recording

@router.put("/{recording_id}/speakers")
def update_speaker(recording_id: int, request: UpdateSpeakerRequest, db: Session = Depends(get_db)):
    # Find transcript
    transcript = db.query(Transcript).filter(Transcript.recording_id == recording_id).first()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    
    content = transcript.content
    if not content or not isinstance(content, list):
         raise HTTPException(status_code=400, detail="Invalid transcript content")
    
    updated_count = 0
    new_content = []
    
    # Iterate and update
    for segment in content:
        if segment.get("speaker_id") == request.original_speaker_id:
            segment["speaker_id"] = request.new_speaker_id
            updated_count += 1
        new_content.append(segment)
            
    if updated_count == 0:
        return {"message": "No speakers updated", "updated_count": 0}
        
    # Update DB
    # Force SQLAlchemy to detect change by assigning a new list
    transcript.content = list(new_content)
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(transcript, "content")

    # Also update plain_text to reflect new names? 
    # Current plain text format: "Speaker X: text"
    # It's better to update plain_text too for consistency in search/display if fallback
    if transcript.plain_text:
        transcript.plain_text = transcript.plain_text.replace(
            f"{request.original_speaker_id}:", 
            f"{request.new_speaker_id}:"
        )
    
    db.add(transcript)
    db.commit()
    db.refresh(transcript)
    
    return {"message": "Speaker updated", "updated_count": updated_count, "content": transcript.content}
