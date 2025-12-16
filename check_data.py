import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(r"C:\AI\meetmind\.env")

db_url = os.getenv("DATABASE_URL")
print(f"Connecting to: {db_url}")

try:
    engine = create_engine(db_url)
    with engine.connect() as connection:
        result = connection.execute(text("SELECT * FROM projects"))
        projects = result.fetchall()
        print(f"Found {len(projects)} projects.")
        for p in projects:
            print(f" - {p}")
            
        # Also check recordings
        result = connection.execute(text("SELECT * FROM recordings"))
        recordings = result.fetchall()
        print(f"Found {len(recordings)} recordings.")
        
except Exception as e:
    print(f"Error: {e}")
