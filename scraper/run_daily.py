# scraper/run_daily.py
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
        await page.wait_for_timeout(2000)  # small wait for rendering

        # ✅ Use your verified selectors from scrapy
        job_cards = await page.query_selector_all("div.job_seen_beacon, a.tapItem")
        print(f"✅ Found {len(job_cards)} job cards")

        for card in job_cards:
            title = await card.locator("h2.jobTitle span, h2 span, a[aria-label]").text_content().catch(lambda _: None)
            company = await card.locator("span.companyName, span[data-testid='company-name']").text_content().catch(lambda _: None)
            location_parts = await card.locator("div.companyLocation *, div[data-testid='text-location'] *").all_text_contents()
            location = " ".join(p.strip() for p in location_parts if p.strip())

            salary_parts = await card.locator(
                "div[data-testid='salary-snippet-container'] span, "
                "div[id='salaryInfoAndJobType'] span, "
                "div[data-testid='attribute_snippet_text'], "
                "span.css-1oc7tea"
            ).all_text_contents()
            salary = " ".join(p.strip() for p in salary_parts if p.strip()) or "Not disclosed"

            job_url = await card.locator("a").first.get_attribute("href")
            if job_url and job_url.startswith("/"):
                job_url = urljoin("https://www.indeed.com", job_url)

            print(f"Title: {title}, Company: {company}, URL: {job_url}") 

            if title and company and job_url:
                job_data = {
                    "title": title.strip(),
                    "company": company.strip(),
                    "location": location.strip(),
                    "salary": salary.strip(),
                    "url": job_url,
                    "description": "",
                    "posted": datetime.now().strftime("%Y-%m-%d"),
                }
                await upsert_job(job_data)

        print("🎉 Jobs scraped and saved successfully!")

    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

    print("✅ Scraping completed — check jobs.db for results.")

if __name__ == "__main__":
    asyncio.run(run())
