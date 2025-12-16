from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import engine, Base
import models
from routers import projects, recordings
import os
import mimetypes

# Create tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="MeetMind API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(recordings.router)

# Custom media handler with Range support
MEDIA_DIR = "/app/media"
if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)

@app.get("/media/{file_path:path}")
async def get_media(file_path: str, request: Request, range: str = Header(None)):
    file_full_path = os.path.join(MEDIA_DIR, file_path)
    if not os.path.exists(file_full_path):
         raise HTTPException(status_code=404, detail="File not found")
    
    # Simple mimetype detection
    media_type, _ = mimetypes.guess_type(file_full_path)
    if not media_type:
        media_type = "application/octet-stream"

    file_size = os.path.getsize(file_full_path)
    
    # Handle Range header
    if range:
        try:
            start, end = range.replace("bytes=", "").split("-")
            start = int(start)
            end = int(end) if end else file_size - 1
        except ValueError:
            start = 0
            end = file_size - 1
            
        if start >= file_size:
            raise HTTPException(status_code=416, detail="Range Not Satisfiable")
            
        end = min(end, file_size - 1)
        chunk_size = end - start + 1
        
        def iterfile():
            with open(file_full_path, "rb") as f:
                f.seek(start)
                bytes_read = 0
                while bytes_read < chunk_size:
                    chunk = f.read(min(1024*1024, chunk_size - bytes_read)) # 1MB chunks
                    if not chunk:
                        break
                    bytes_read += len(chunk)
                    yield chunk
                    
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
        }
        
        return StreamingResponse(iterfile(), status_code=206, media_type=media_type, headers=headers)
    
    # Default behavior for non-range requests
    return FileResponse(file_full_path, media_type=media_type, headers={"Accept-Ranges": "bytes"})

# Remove StaticFiles mount as we are handling it manually
# app.mount("/media", StaticFiles(directory="/app/media"), name="media")

@app.get("/")
def read_root():
    return {"message": "MeetMind API is running"}
