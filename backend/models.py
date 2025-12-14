from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship
from database import Base
import datetime
import enum

class RecordingStatus(str, enum.Enum):
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    ERROR = "error"

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    recordings = relationship("Recording", back_populates="project", cascade="all, delete-orphan")

class Recording(Base):
    __tablename__ = "recordings"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    filename = Column(String(255))
    file_path = Column(String(512)) # Path in the container/volume
    duration = Column(Integer, nullable=True) # In seconds
    status = Column(Enum(RecordingStatus), default=RecordingStatus.PENDING)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("Project", back_populates="recordings")
    transcript = relationship("Transcript", back_populates="recording", uselist=False, cascade="all, delete-orphan")
    minutes = relationship("MeetingMinutes", back_populates="recording", uselist=False, cascade="all, delete-orphan")

class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)
    recording_id = Column(Integer, ForeignKey("recordings.id"))
    content = Column(JSON) # List of segments: {start, end, text, speaker_id}
    plain_text = Column(LONGTEXT) # Full text for search/display
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    recording = relationship("Recording", back_populates="transcript")

class MeetingMinutes(Base):
    __tablename__ = "meeting_minutes"

    id = Column(Integer, primary_key=True, index=True)
    recording_id = Column(Integer, ForeignKey("recordings.id"))
    content = Column(Text) # Markdown content
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    recording = relationship("Recording", back_populates="minutes")
