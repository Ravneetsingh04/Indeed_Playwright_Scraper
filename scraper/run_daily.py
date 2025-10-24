# scraper/run_daily.py
import asyncio
from scraper.playwright_client import create_stealth_context
from scraper.storage import init_db, upsert_job

async def run():
    await init_db()  # make sure DB exists
    playwright, browser, context, page = await create_stealth_context(headless=True)
    try:
        await page.goto("https://www.indeed.com/jobs?q=software+engineer&l=", wait_until="domcontentloaded")
        title = await page.title()
        print(f"✅ Page loaded successfully: {title}")
        # Here you can extract and save jobs using your parsers
        await upsert_job({
            "url": "https://www.indeed.com",
            "title": title,
            "company": "Test Company",
            "location": "Remote",
            "description": "Dummy record for validation."
        })
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()
    print("✅ Daily scrape completed successfully.")

if __name__ == "__main__":
    asyncio.run(run())
