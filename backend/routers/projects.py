from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models import Project, Recording, MeetingMinutes, ProjectKnowledgeBase, Transcript, ChatSession, ChatMessage
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import datetime
from services.llm import LLMService
from services.agents import KnowledgeBaseOrchestrator
from services.qa_agent import ProjectQAAgent
from database import SessionLocal
import json
from auth import get_current_user
from models import User

router = APIRouter(prefix="/projects", tags=["projects"])

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectOut(ProjectBase):
    id: int
    created_at: datetime.datetime
    
    class Config:
        orm_mode = True

class GenerateKBRequest(BaseModel):
    minutes_ids: List[int]

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
    if not minutes:
         raise HTTPException(status_code=400, detail="No valid minutes found")

    # We will stream the generation of ONE section or ALL sections sequentially.
    # To keep it simple for SSE, let's stream one by one, but maybe frontend wants to trigger them individually?
    # Or we can stream a structured event: "event: prd\ndata: chunk..."
    
    # For simplicity, let's just stream ALL of them sequentially with event separators.
    
    def event_generator():
        llm_service = LLMService()
        orchestrator = KnowledgeBaseOrchestrator(llm_service)
        context = orchestrator.build_context(minutes)
        
        tasks = ["prd", "specs", "timeline", "glossary"]
        
        # We need to save the final result to DB as well.
        full_content = {}

        for task in tasks:
            yield f"event: start_section\ndata: {task}\n\n"
            
            section_content = ""
            stream = orchestrator.run_worker_agent_stream(task, context)
            
            for chunk in stream:
                section_content += chunk
                # SSE format: data: <content>\n\n
                # We need to escape newlines in data or just send raw chunks if client handles it.
                # Standard SSE: data: payload
                # If payload has newlines, it's multiple data lines.
                # Let's use JSON for safety.
                import json
                yield f"event: chunk\ndata: {json.dumps({'section': task, 'chunk': chunk})}\n\n"
            
            full_content[task] = section_content
            yield f"event: end_section\ndata: {task}\n\n"

        # After all done, save to DB in this thread (blocking but okay for generator final step)
        # Re-create session for this thread since the generator runs later
        try:
            db_local = SessionLocal()
            kb = db_local.query(ProjectKnowledgeBase).filter(ProjectKnowledgeBase.project_id == project_id).first()
            if not kb:
                kb = ProjectKnowledgeBase(project_id=project_id, content=full_content)
                db_local.add(kb)
            else:
                kb.content = full_content
                kb.updated_at = datetime.datetime.utcnow()
            db_local.commit()
            db_local.close()
            yield f"event: done\ndata: saved\n\n"
        except Exception as e:
            print(f"Error saving KB: {e}")
            yield f"event: error\ndata: {str(e)}\n\n"

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

    # Load Knowledge Base
    kb = db.query(ProjectKnowledgeBase).filter(ProjectKnowledgeBase.project_id == project_id).first()
    kb_content = kb.content if kb else {}

    # Load Minutes
    from sqlalchemy.orm import joinedload
    minutes = db.query(MeetingMinutes).options(joinedload(MeetingMinutes.recording)).join(Recording).filter(Recording.project_id == project_id).all()
    
    minutes_data = []
    for m in minutes:
        minutes_data.append({
            "content": m.content,
            "created_at": m.recording.created_at.strftime("%Y-%m-%d") if m.recording else str(m.created_at),
            "recording_id": m.recording_id
        })

    # Load Transcripts
    transcripts = db.query(Transcript).join(Recording).filter(Recording.project_id == project_id).all()
    transcripts_data = []
    for t in transcripts:
        if t.plain_text:
            transcripts_data.append({
                "id": t.id,
                "content": t.plain_text,
                "created_at": t.recording.created_at.strftime("%Y-%m-%d") if t.recording else str(t.created_at),
                "recording_id": t.recording_id
            })

    def stream_agent():
        llm_service = LLMService()
        agent = ProjectQAAgent(llm_service, kb_content, minutes_data, transcripts_data)
        
        full_answer = ""
        thoughts = []
        
        # Use generator from agent
        for event in agent.run_stream(request.query):
            # Capture content for saving to DB
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
        
        # Save Assistant Message to DB after stream ends
        # We need a new DB session here because the generator runs in a different context/thread usually, 
        # or just to be safe with long running streams.
        try:
            db_local = SessionLocal()
            assistant_msg = ChatMessage(
                session_id=session_id, 
                role="assistant", 
                content=full_answer,
                thought_process=thoughts
            )
            db_local.add(assistant_msg)
            
            # Update session title if it's "New Chat" and this is the first exchange
            session = db_local.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session and session.title == "New Chat":
                session.title = request.query[:30]
                session.updated_at = datetime.datetime.utcnow()
            else:
                session.updated_at = datetime.datetime.utcnow()
                
            db_local.commit()
            db_local.close()
            
            # Send session_id back to client so they can switch URL if needed
            yield f"event: session_id\ndata: {json.dumps({'id': session_id})}\n\n"
            
        except Exception as e:
            print(f"Error saving chat message: {e}")

    return StreamingResponse(stream_agent(), media_type="text/event-stream")
