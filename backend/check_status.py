from database import SessionLocal
from models import Recording, Transcript

db = SessionLocal()
recording = db.query(Recording).order_by(Recording.created_at.desc()).first()
if recording:
    print(f"ID: {recording.id}")
    print(f"Filename: {recording.filename}")
    print(f"Status: {recording.status}")
    print(f"Transcript exists: {recording.transcript is not None}")
    if recording.transcript:
        print(f"Transcript content len: {len(recording.transcript.content) if recording.transcript.content else 0}")
else:
    print("No recordings found")
db.close()
