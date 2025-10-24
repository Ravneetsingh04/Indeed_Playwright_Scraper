import os

structure = [
    "scraper",
    "scraper/tests",
    ".github/workflows"
]

files = [
    "scraper/__init__.py",
    "scraper/config.py",
    "scraper/playwright_client.py",
    "scraper/workers.py",
    "scraper/parsers.py",
    "scraper/storage.py",
    "requirements.txt",
    "README.md",
    ".github/workflows/schedule.yml"
]

for folder in structure:
    os.makedirs(folder, exist_ok=True)

for file in files:
    open(file, "a").close()

print("✅ Project structure created successfully.")
