from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models import Project, Recording, MeetingMinutes, ProjectKnowledgeBase, Transcript, ChatSession, ChatMessage, ProjectDocument, ProjectDocumentType
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import datetime
import os
import uuid
import shutil
from services.llm import LLMService
from services.agents import KnowledgeBaseOrchestrator
from services.deep_research import DeepResearchService
from services.qa_agent import ProjectQAAgent
from database import SessionLocal
import json
from auth import get_current_user
from models import User
from services.aliyun import AliyunService

router = APIRouter(prefix="/projects", tags=["projects"])

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectOut(ProjectBase):
    id: int
    created_at: datetime.datetime
    hotwords: Optional[List[Dict[str, Any]]] = None
    vocabulary_id: Optional[str] = None
    
    class Config:
        orm_mode = True

class Hotword(BaseModel):
    text: str
    weight: int = 4
    lang: str = "zh"

class ProjectSettingsUpdate(BaseModel):
    hotwords: List[Hotword]

class GenerateKBRequest(BaseModel):
    minutes_ids: List[int]
    document_ids: Optional[List[int]] = []

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[int] = None

class ChatSessionOut(BaseModel):
    id: int
    title: str
    created_at: datetime.datetime
    
    class Config:
        orm_mode = True

class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    thought_process: Optional[List[str]] = None
    created_at: datetime.datetime

    class Config:
        orm_mode = True

class ProjectDocumentOut(BaseModel):
    id: int
    project_id: int
    filename: str
    file_type: str
    created_at: datetime.datetime

    class Config:
        orm_mode = True

def _generate_kb_task(project_id: int, minutes_ids: List[int]):
    db = SessionLocal()
    try:
        # Join with Recording to ensure we can sort by date
        minutes = db.query(MeetingMinutes).join(Recording).filter(MeetingMinutes.id.in_(minutes_ids)).all()
        
        if not minutes:
            print(f"No minutes found for IDs: {minutes_ids}")
            return

        llm_service = LLMService()
        orchestrator = KnowledgeBaseOrchestrator(llm_service)
        results = orchestrator.generate_knowledge_base(minutes)
        
        # Save to DB
        kb = db.query(ProjectKnowledgeBase).filter(ProjectKnowledgeBase.project_id == project_id).first()
        if not kb:
            kb = ProjectKnowledgeBase(project_id=project_id, content=results)
            db.add(kb)
        else:
            kb.content = results
            kb.updated_at = datetime.datetime.utcnow()
        db.commit()
        print(f"Knowledge Base generated for project {project_id}")
    except Exception as e:
        print(f"Error generating KB: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

@router.post("/{project_id}/knowledge-base/generate")
def generate_knowledge_base(
    project_id: int, 
    request: GenerateKBRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    background_tasks.add_task(_generate_kb_task, project_id, request.minutes_ids)
    return {"message": "Knowledge base generation started"}

@router.post("/{project_id}/knowledge-base/generate/stream")
def generate_knowledge_base_stream(
    project_id: int, 
    request: GenerateKBRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Use joinedload to eagerly load the recording relationship to avoid DetachedInstanceError in the generator thread
    from sqlalchemy.orm import joinedload
    minutes = db.query(MeetingMinutes).options(joinedload(MeetingMinutes.recording)).join(Recording).filter(MeetingMinutes.id.in_(request.minutes_ids)).all()
    
    # Fetch documents
    documents = []
    if request.document_ids:
        documents = db.query(ProjectDocument).filter(ProjectDocument.id.in_(request.document_ids)).all()
    
    if not minutes and not documents:
         raise HTTPException(status_code=400, detail="No valid minutes or documents found")

    # We will stream the generation of ONE section or ALL sections sequentially.
    # To keep it simple for SSE, let's stream one by one, but maybe frontend wants to trigger them individually?
    # Or we can stream a structured event: "event: prd\ndata: chunk..."
    
    # For simplicity, let's just stream ALL of them sequentially with event separators.
    
    def event_generator():
        try:
            # Pass full structure to DeepResearch for better citations
            minutes_data = []
            for m in minutes:
                if m.content and m.recording:
                    minutes_data.append({
                        "content": m.content,
                        "id": m.recording_id,
                        "filename": m.recording.filename
                    })
            
            documents_data = []
            for d in documents:
                documents_data.append({
                    "id": d.id,
                    "filename": d.filename,
                    "type": d.file_type,
                    "gemini_uri": d.gemini_file_uri,
                    # We don't have text content for documents yet, but we pass URI.
                    # DeepResearch service handles URI or text content.
                    "content": None 
                })

            service = DeepResearchService()
            interaction_id = service.start_research(minutes_data, documents_data)
            
            full_text = ""
            
            for update in service.stream_research_updates(interaction_id):
                if update["status"] == "running":
                    yield f"event: status\ndata: {json.dumps({'message': update['message']})}\n\n"
                elif update["status"] == "completed":
                    full_text = update["result"]
                elif update["status"] == "failed":
                    yield f"event: error\ndata: {json.dumps({'message': update['message']})}\n\n"
                    return

            # Parse and save
            parsed_content = service.parse_result(full_text)
            
            # Save to DB
            try:
                db_local = SessionLocal()
                kb = db_local.query(ProjectKnowledgeBase).filter(ProjectKnowledgeBase.project_id == project_id).first()
                
                # We can also try to upload sections to Gemini if needed, 
                # but Deep Research result is already one big text. 
                # For now, we skip individual section upload or implement it later.
                
                if not kb:
                    kb = ProjectKnowledgeBase(project_id=project_id, content=parsed_content)
                    db_local.add(kb)
                else:
                    kb.content = parsed_content
                    kb.updated_at = datetime.datetime.utcnow()
                db_local.commit()
                db_local.close()
            except Exception as e:
                print(f"DB Error: {e}")
            
            yield f"event: done\ndata: {json.dumps({'content': parsed_content})}\n\n"

        except Exception as e:
            print(f"Generator Error: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/{project_id}/knowledge-base")
def get_knowledge_base(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    kb = db.query(ProjectKnowledgeBase).filter(ProjectKnowledgeBase.project_id == project_id).first()
    if not kb:
        return {"content": None}
    return kb

@router.post("/", response_model=ProjectOut)
def create_project(project: ProjectCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_project = Project(name=project.name, description=project.description)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@router.get("/", response_model=List[ProjectOut])
def list_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    projects = db.query(Project).offset(skip).limit(limit).all()
    return projects

@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.patch("/{project_id}/hotwords")
def update_project_hotwords(
    project_id: int, 
    settings: ProjectSettingsUpdate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Convert Pydantic models to list of dicts
    # Filter to only allowed keys for Aliyun Vocabulary
    hotwords_list = []
    for h in settings.hotwords:
        item = {"text": h.text, "weight": h.weight}
        hotwords_list.append(item)
    
    print(f"DEBUG: Updating hotwords for project {project_id}: {hotwords_list}")
    
    # Save to DB first (we can store the full object including lang if we want, but for now hotwords column is JSON)
    # If we want to persist 'lang' in DB but not send to Aliyun, we should use the original list for DB
    db_hotwords = [h.dict() for h in settings.hotwords]
    project.hotwords = db_hotwords
    
    # Update Aliyun
    try:
        if hotwords_list:
            # We prefix with prj{id} to avoid collisions if we were using same account for multiple projects
            # Prefix must be alphanumeric
            vocab_id = AliyunService.create_vocabulary(hotwords_list, prefix=f"prj{project_id}")
            project.vocabulary_id = vocab_id
        else:
            # If cleared, we don't necessarily delete the vocab on Aliyun (no delete API in this scope), 
            # but we remove the ID from project so it won't be used.
            project.vocabulary_id = None
            
    except Exception as e:
        print(f"Failed to sync with Aliyun: {e}")
        # Fail the request so user knows it didn't sync
        raise HTTPException(status_code=500, detail=f"Failed to sync hotwords with cloud: {str(e)}")

    db.commit()
    db.refresh(project)
    return {"message": "Hotwords updated", "vocabulary_id": project.vocabulary_id}

@router.post("/{project_id}/chat/sessions", response_model=ChatSessionOut)
def create_chat_session(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    session = ChatSession(project_id=project_id, title="New Chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

@router.get("/{project_id}/chat/sessions", response_model=List[ChatSessionOut])
def list_chat_sessions(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sessions = db.query(ChatSession).filter(ChatSession.project_id == project_id).order_by(ChatSession.updated_at.desc()).all()
    return sessions

@router.get("/chat/sessions/{session_id}/messages", response_model=List[ChatMessageOut])
def get_session_messages(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Verify session exists
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()
    
    # Parse thought_process JSON if it exists
    result = []
    for msg in messages:
        thoughts = None
        if msg.thought_process is not None:
            if isinstance(msg.thought_process, list):
                thoughts = msg.thought_process
            elif isinstance(msg.thought_process, str):
                try:
                    thoughts = json.loads(msg.thought_process)
                except:
                    thoughts = []
        
        result.append(ChatMessageOut(
            id=msg.id,
            role=msg.role,
            content=msg.content if msg.content is not None else "",
            thought_process=thoughts,
            created_at=msg.created_at
        ))
    return result

@router.post("/{project_id}/documents", response_model=ProjectDocumentOut)
def upload_document(
    project_id: int, 
    file: UploadFile = File(...), 
    file_type: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    UPLOAD_DIR = "/app/media"
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)

    file_ext = file.filename.split(".")[-1]
    unique_filename = f"doc_{uuid.uuid4()}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Upload to Gemini
    llm_service = LLMService()
    
    # Map common extensions to MIME types if needed (FastAPI UploadFile.content_type is usually reliable but sometimes generic)
    mime_type = file.content_type
    if not mime_type or mime_type == "application/octet-stream":
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file.filename)
        
    gemini_uri = llm_service.upload_file_path_to_gemini(
        file_path, 
        mime_type=mime_type, 
        display_name=f"{file_type}_{file.filename}"
    )

    db_doc = ProjectDocument(
        project_id=project_id,
        filename=file.filename,
        file_path=file_path,
        file_type=file_type,
        gemini_file_uri=gemini_uri
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc

@router.get("/{project_id}/documents", response_model=List[ProjectDocumentOut])
def list_documents(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(ProjectDocument).filter(ProjectDocument.project_id == project_id).order_by(ProjectDocument.created_at.desc()).all()

@router.delete("/{project_id}/documents/{doc_id}", status_code=204)
def delete_document(project_id: int, doc_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(ProjectDocument).filter(ProjectDocument.id == doc_id, ProjectDocument.project_id == project_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except:
            pass
            
    db.delete(doc)
    db.commit()
    return None

@router.post("/{project_id}/chat")
def chat_with_project(
    project_id: int, 
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get or create session
    session_id = request.session_id
    if not session_id:
        new_session = ChatSession(project_id=project_id, title=request.query[:30])
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        session_id = new_session.id
    
    # Save User Message
    user_msg = ChatMessage(session_id=session_id, role="user", content=request.query)
    db.add(user_msg)
    db.commit()

    # Gather File URIs for Gemini
    file_uris = []
    
    # KB Files
    kb = db.query(ProjectKnowledgeBase).filter(ProjectKnowledgeBase.project_id == project_id).first()
    kb_content = kb.content if kb else {}
    if kb and kb.gemini_files:
        if isinstance(kb.gemini_files, dict):
            file_uris.extend(kb.gemini_files.values())
        elif isinstance(kb.gemini_files, list):
            file_uris.extend(kb.gemini_files)

    # Minutes Files
    from sqlalchemy.orm import joinedload
    minutes = db.query(MeetingMinutes).options(joinedload(MeetingMinutes.recording)).join(Recording).filter(Recording.project_id == project_id).all()
    
    minutes_data = []
    for m in minutes:
        if m.gemini_file_uri:
            file_uris.append(m.gemini_file_uri)
        # Fallback data for old agent
        minutes_data.append({
            "content": m.content,
            "created_at": m.recording.created_at.strftime("%Y-%m-%d") if m.recording else str(m.created_at),
            "recording_id": m.recording_id
        })

    # Transcript Files
    transcripts = db.query(Transcript).join(Recording).filter(Recording.project_id == project_id).all()
    transcripts_data = []
    for t in transcripts:
        if t.gemini_file_uri:
            file_uris.append(t.gemini_file_uri)
        # Fallback data for old agent
        if t.plain_text:
            transcripts_data.append({
                "id": t.id,
                "content": t.plain_text,
                "created_at": t.recording.created_at.strftime("%Y-%m-%d") if t.recording else str(t.created_at),
                "recording_id": t.recording_id
            })
    
    # Project Documents
    docs = db.query(ProjectDocument).filter(ProjectDocument.project_id == project_id).all()
    for doc in docs:
        if doc.gemini_file_uri:
            file_uris.append(doc.gemini_file_uri)

    # Load Chat History for Context
    # Limit to last 20 messages to fit context
    history_msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()
    
    chat_history = []
    for msg in history_msgs:
        chat_history.append({"role": msg.role, "content": msg.content})

    def stream_agent():
        llm_service = LLMService()
        
        full_answer = ""
        thoughts = []
        
        if llm_service.use_google and file_uris:
            # Use Gemini Native Chat with Files
            # We add a system prompt to guide it
            system_msg = {
                "role": "system", 
                "content": "You are a project assistant. Use the provided project documents, meeting minutes, and transcripts to answer the user's questions accurately. Quote sources if possible. ALWAYS reply in the same language as the user's question (e.g., if user asks in Chinese, reply in Chinese)."
            }
            messages = [system_msg] + chat_history
            
            try:
                # We yield a "thought" event just to indicate we are searching/thinking
                yield f"event: thought\ndata: {json.dumps({'content': 'Retrieving project knowledge...'})}\n\n"
                
                for chunk in llm_service.chat_with_files(messages, file_uris):
                    # Check for error
                    if chunk.startswith("\n\n**Error"):
                        yield f"event: error\ndata: {json.dumps({'content': chunk})}\n\n"
                    else:
                        full_answer += chunk
                        # Ensure chunk is properly JSON dumped
                        yield f"event: answer\ndata: {json.dumps({'content': chunk})}\n\n"
                        # Force flush if possible by yielding an empty comment line? No, FastAPI/Starlette should handle it.
                        # But adding a small sleep might help debugging if it's too fast? No.
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'content': str(e)})}\n\n"
        
        else:
            # Fallback to old ProjectQAAgent (ReAct)
            agent = ProjectQAAgent(llm_service, kb_content, minutes_data, transcripts_data)
            for event in agent.run_stream(request.query):
                if event.startswith("event: thought"):
                    try:
                        data = json.loads(event.split("data: ")[1])
                        thoughts.append(data.get("content", ""))
                    except: pass
                elif event.startswith("event: answer"):
                    try:
                        data = json.loads(event.split("data: ")[1])
                        full_answer = data.get("content", "")
                    except: pass
                yield event
        
        # Save Assistant Message to DB
        try:
            db_local = SessionLocal()
            assistant_msg = ChatMessage(
                session_id=session_id, 
                role="assistant", 
                content=full_answer,
                thought_process=thoughts
            )
            db_local.add(assistant_msg)
            
            session = db_local.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                session.updated_at = datetime.datetime.utcnow()
                if session.title == "New Chat":
                    session.title = request.query[:30]
            
            db_local.commit()
            db_local.close()
            
            yield f"event: session_id\ndata: {json.dumps({'id': session_id})}\n\n"
            
        except Exception as e:
            print(f"Error saving chat message: {e}")

    return StreamingResponse(stream_agent(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})
