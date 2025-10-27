import asyncio
from datetime import datetime
from urllib.parse import urlencode, urljoin
from scraper.playwright_client import create_stealth_context
from scraper.storage import init_db, upsert_job

BASE_URL = "https://www.indeed.com/jobs?"

SEARCH_TERM = "Python Developer"
LOCATION = "New York, NY"

async def run():
    await init_db()
    playwright, browser, context, page = await create_stealth_context(headless=True)

    try:
        params = {"q": SEARCH_TERM, "l": LOCATION, "fromage": 1}
        url = BASE_URL + urlencode(params)
        print(f"➡️ Visiting: {url}")

        await page.goto(url, wait_until="domcontentloaded")
        # Handle potential cookie or consent popups
        try:
            await page.locator("button:has-text('Accept')").click(timeout=3000)
            print("🍪 Accepted cookies popup")
        except Exception:
            pass

        await page.wait_for_selector("div.cardOutline, div.job_seen_beacon", timeout=30000)
        
        html = await page.content()
        if "cardOutline" not in html:
            print("⚠️ cardOutline not found — page may have loaded differently or was blocked")



        # ✅ Updated Indeed selectors (2025)
        job_cards = await page.query_selector_all("div.cardOutline.tapItem")
        print(f"✅ Found {len(job_cards)} job cards")

        for card in job_cards:
            # Extract job title
            title_el = await card.query_selector("h2.jobTitle span[title]")
            title = await title_el.text_content() if title_el else None

            # Extract company name
            company_el = await card.query_selector("span[data-testid='company-name']")
            company = await company_el.text_content() if company_el else None

            # Extract location
            location_el = await card.query_selector("div[data-testid='text-location']")
            location = await location_el.text_content() if location_el else None

            # Extract job link
            link_el = await card.query_selector("a.jcs-JobTitle")
            job_url = await link_el.get_attribute("href") if link_el else None
            if job_url and job_url.startswith("/"):
                job_url = urljoin("https://www.indeed.com", job_url)

            # Only insert valid jobs
            if title and company and job_url:
                job_data = {
                    "url": job_url,
                    "title": title.strip(),
                    "company": company.strip(),
                    "location": (location or "").strip(),
                    "description": "",
                }
                print("📝 Scraped job:", job_data["title"], "-", job_data["company"])
                await upsert_job(job_data)

        print("🎉 Jobs scraped and saved successfully!")

    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

    print("✅ Scraping completed — check jobs.db for results.")

if __name__ == "__main__":
    asyncio.run(run())
