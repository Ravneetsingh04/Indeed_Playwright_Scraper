import aiosqlite
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB= os.path.join(BASE_DIR, "jobs.db")

CREATE = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,
    title TEXT,
    company TEXT,
    location TEXT,
    description TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute(CREATE)
        await db.commit()

async def upsert_job(job):
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            INSERT INTO jobs (url, title, company, location, description)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
              title=excluded.title, company=excluded.company, location=excluded.location, description=excluded.description, scraped_at=CURRENT_TIMESTAMP
        """, (job.get("url"), job.get("title"), job.get("company"), job.get("location"), job.get("description")))
        await db.commit()
