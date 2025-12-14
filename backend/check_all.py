from database import SessionLocal
from models import Recording

db = SessionLocal()
recordings = db.query(Recording).all()
for r in recordings:
    print(f"ID: {r.id}, File: {r.filename}, Status: {r.status}, HasTranscript: {r.transcript is not None}")
db.close()
