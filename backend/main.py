from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import engine, Base
import models
from routers import projects, recordings
import os

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

# Mount media directory
if not os.path.exists("/app/media"):
    os.makedirs("/app/media")
app.mount("/media", StaticFiles(directory="/app/media"), name="media")

@app.get("/")
def read_root():
    return {"message": "MeetMind API is running"}
