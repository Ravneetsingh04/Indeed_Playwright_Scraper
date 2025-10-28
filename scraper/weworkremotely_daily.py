"""
scraper/weworkremotely_daily.py

Daily runner for the WeWorkRemotely Playwright scraper.
This script:
 - Runs the Playwright-based WWR scraper
 - (Optionally) runs any other scrapers
 - Writes results into jobs.db (SQLite)
 - Designed to be invoked by GitHub Actions workflow:
       python -m scraper.weworkremotely_daily
"""

import sqlite3
import os
import sys
from datetime import datetime
import importlib

DB_PATH = os.getenv("JOBS_DB_PATH", "jobs.db")


def ensure_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            title TEXT,
            company TEXT,
            location TEXT,
            posted TEXT,
            salary TEXT,
            url TEXT UNIQUE,
            snippet TEXT,
            scraped_at TEXT
        )
        """
    )
    conn.commit()
    return conn


def insert_jobs(conn, source, rows):
    cur = conn.cursor()
    inserted, skipped = 0, 0
    now = datetime.utcnow().isoformat()
    for r in rows:
        url = r.get("url")
        if not url:
            skipped += 1
            continue
        try:
            cur.execute(
                """
                INSERT INTO jobs (source, title, company, location, posted, salary, url, snippet, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    r.get("title"),
                    r.get("company"),
                    r.get("location"),
                    r.get("posted") or "",
                    r.get("salary") or "Not disclosed",
                    url,
                    r.get("snippet", "")[:2000] if r.get("snippet") else "",
                    now,
                ),
            )
            conn.commit()
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    return inserted, skipped


def run_weworkremotely_scraper():
    """Run the Playwright-based WWR scraper and return a list of job dicts."""
    try:
        mod = importlib.import_module("scraper.weworkremotely_playwright")
    except Exception as e:
        print("❌ Could not import weworkremotely_playwright:", e, file=sys.stderr)
        return []

    try:
        cls = getattr(mod, "WeWorkRemotelyPlaywright", None)
        if cls:
            crawler = cls(headless=True)
            return crawler.run()
    except Exception as e:
        print("⚠️ Error running WeWorkRemotelyPlaywright:", e, file=sys.stderr)

    print("⚠️ No valid entry point found in weworkremotely_playwright.py")
    return []


def main():
    conn = ensure_db(DB_PATH)
    print("🚀 Starting WeWorkRemotely Playwright daily scrape...")

    jobs = run_weworkremotely_scraper()
    print(f"✅ Scraped {len(jobs)} jobs from WeWorkRemotely")

    inserted, skipped = insert_jobs(conn, "weworkremotely", jobs)
    conn.close()

    print(f"🧾 Database updated: {inserted} inserted, {skipped} skipped (duplicates)")
    print(f"📁 jobs.db located at: {os.path.abspath(DB_PATH)}")


if __name__ == "__main__":
    main()
