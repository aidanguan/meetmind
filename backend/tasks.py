from celery_worker import celery_app
from database import SessionLocal
from models import Recording, RecordingStatus, Transcript, MeetingMinutes, Project
from services.aliyun import AliyunService
from services.llm import LLMService
from services.oss import OSSService
import time
import json
import os
import redis

@celery_app.task(name="tasks.transcribe_audio")
def transcribe_audio(recording_id: int):
    db = SessionLocal()
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    
    if not recording:
        db.close()
        return "Recording not found"

    recording.status = RecordingStatus.TRANSCRIBING
    db.commit()

    try:
        # Check multiple env names to decide real vs mock
        aliyun_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIYUN_TOKEN") or os.getenv("ALIYUN_APPKEY")
        if aliyun_key:
            # Fetch Project to get vocabulary_id
            project = db.query(Project).filter(Project.id == recording.project_id).first()
            vocabulary_id = project.vocabulary_id if project else None
            
            print(f"DEBUG: Starting transcription for recording {recording.id} with vocabulary_id: {vocabulary_id}")

            # Real Call with retries
            attempts = 0
            max_attempts = 3
            last_error = None
            result = None
            while attempts < max_attempts:
                try:
                    object_name, file_url = OSSService.upload_file(recording.file_path)
                    task_response = AliyunService.transcribe(file_url=file_url, vocabulary_id=vocabulary_id)
                    result = AliyunService.get_task_result(task_response.output.task_id)
                    print(f"DEBUG: DashScope Result: {result}")
                    if getattr(result.output, "task_status", "") == "SUCCEEDED":
                        break
                    raise Exception(f"Transcription failed: {result.output}")
                except Exception as e:
                    last_error = e
                    attempts += 1
                    if attempts < max_attempts:
                        time.sleep(2 * attempts)
                    else:
                        raise e
            
            # Parse result
            results = getattr(result.output, 'results', [])
            sentences = []
            
            # Fetch full result from transcription_url if present
            if results and isinstance(results, list):
                for res in results:
                    transcription_url = res.get('transcription_url') if isinstance(res, dict) else getattr(res, 'transcription_url', None)
                    if transcription_url:
                        import requests
                        try:
                            print(f"DEBUG: Fetching transcription from URL: {transcription_url}")
                            resp = requests.get(transcription_url)
                            if resp.status_code == 200:
                                data = resp.json()
                                # Structure: { "transcripts": [ { "sentences": [...] } ] }
                                if 'transcripts' in data:
                                    for t in data['transcripts']:
                                        if 'sentences' in t:
                                            sentences.extend(t['sentences'])
                            else:
                                print(f"Error fetching transcription URL: {resp.status_code}")
                        except Exception as e:
                             print(f"Error downloading transcription result: {e}")

                    # Fallback to direct sentences if available (usually not for async tasks)
                    elif hasattr(res, 'sentences'):
                         sentences.extend(res.sentences)
                    elif isinstance(res, dict) and 'sentences' in res:
                         sentences.extend(res['sentences'])

            parsed_content = []
            plain_text_parts = []
            
            for sent in sentences:
                # Handle attribute or dict access
                text = sent.get('text', '')
                start = sent.get('begin_time', 0)
                end = sent.get('end_time', 0)
                speaker = sent.get('speaker_id', 'Unknown')
                
                parsed_content.append({
                    "start": start,
                    "end": end,
                    "text": text,
                    "speaker_id": f"Speaker {speaker}"
                })
                plain_text_parts.append(f"Speaker {speaker}: {text}")

            mock_content = parsed_content
            plain_text = "\n".join(plain_text_parts)

        else:
            raise Exception("Transcription unavailable: No DashScope API key configured")

        # Clean up old transcripts if any
        db.query(Transcript).filter(Transcript.recording_id == recording.id).delete()
        
        transcript = Transcript(
            recording_id=recording.id,
            content=mock_content,
            plain_text=plain_text
        )
        
        # Upload to Gemini Files API
        try:
            llm_service = LLMService()
            if llm_service.use_google:
                uri = llm_service.upload_to_gemini(
                    plain_text, 
                    mime_type="text/plain", 
                    display_name=f"Transcript_{recording.filename}_{recording.id}"
                )
                if uri:
                    transcript.gemini_file_uri = uri
        except Exception as upload_err:
            print(f"Error uploading transcript to Gemini: {upload_err}")

        db.add(transcript)
        recording.status = RecordingStatus.COMPLETED
        db.commit()
        
    except Exception as e:
        recording.status = RecordingStatus.ERROR
        db.commit()
        print(f"Error in transcription: {e}")
        try:
            r = redis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                db=int(os.getenv("REDIS_DB", "0")),
                decode_responses=True
            )
            r.set(f"recording_error:{recording.id}", str(e), ex=3600)
        except Exception as _:
            pass
    finally:
        db.close()

@celery_app.task(name="tasks.generate_minutes")
def generate_minutes(recording_id: int, context: str = ""):
    db = SessionLocal()
    recording = db.query(Recording).filter(Recording.id == recording_id).first()
    
    if not recording or not recording.transcript:
        db.close()
        return "Recording or transcript not found"

    try:
        llm = LLMService()
        transcript_text = recording.transcript.plain_text
        
        meeting_date = None
        if recording.created_at:
             meeting_date = recording.created_at.strftime("%Y-%m-%d")

        minutes_text = llm.generate_minutes(transcript_text, context, meeting_date=meeting_date)
        
        minutes = MeetingMinutes(
            recording_id=recording.id,
            content=minutes_text
        )

        # Upload to Gemini Files API
        try:
            if llm.use_google:
                uri = llm.upload_to_gemini(
                    minutes_text, 
                    mime_type="text/markdown", 
                    display_name=f"Minutes_{recording.filename}_{recording.id}"
                )
                if uri:
                    minutes.gemini_file_uri = uri
        except Exception as upload_err:
            print(f"Error uploading minutes to Gemini: {upload_err}")

        db.add(minutes)
        db.commit()
    except Exception as e:
        print(f"Error in generating minutes: {e}")
    finally:
        db.close()
