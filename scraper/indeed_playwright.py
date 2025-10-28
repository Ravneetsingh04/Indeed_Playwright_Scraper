# scraper/indeed_playwright.py
import asyncio
from datetime import datetime
from urllib.parse import urlencode, urljoin
from scraper.playwright_client import create_stealth_context
from scraper.storage import init_db, upsert_job
import os

BASE_URL = "https://www.indeed.com/jobs?"
SEARCH_TERM = "Python Developer"
LOCATION = "New York, NY"

async def run():
    await init_db()
    playwright, browser, context, page = await create_stealth_context(headless=True)

    try:
        # --- Build direct Indeed URL ---
        params = {"q": SEARCH_TERM, "l": LOCATION, "fromage": 1}
        url = BASE_URL + urlencode(params)
        print(f"➡️ Visiting: {url}")

        # --- Visit Indeed directly (no ScraperAPI) ---
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
            print(f"⚠️ Page load error: {e}")
            return

        await page.mouse.move(200, 300)
        await page.evaluate("window.scrollBy(0, 800)")
        await page.wait_for_timeout(2000)
        # Explicitly wait for job cards
        await page.wait_for_selector("div.job_seen_beacon, a.tapItem", timeout=15000)

        html = await page.content()
        print("🔍 Page content length:", len(html))
        print("First 500 chars:\n", html[:500])

        # --- Extract Job Cards ---
        job_cards = await page.query_selector_all(
            "div.job_seen_beacon, a.tapItem, div.cardOutline.tapItem"
        )
        if not job_cards:
            print("⚠️ No job cards found — check HTML structure or potential bot detection.")
            snippet = html[:1000]
            print("HTML snippet preview:\n", snippet)
            return

        print(f"✅ Found {len(job_cards)} job cards")
        seen_urls = set()

        for card in job_cards[:10]:  # limit to first 10 for sanity
            # --- Title ---
            try:
                title = (
                    await card.locator("h2.jobTitle span").text_content().catch(lambda _: None)
                    or await card.locator("h2 span").text_content().catch(lambda _: None)
                    or await card.locator("a[aria-label]").get_attribute("aria-label").catch(lambda _: None)
                )
            except Exception:
                title = None

            # --- Company ---
            company_el = await card.query_selector("span.companyName, span[data-testid='company-name']")
            company = await company_el.text_content() if company_el else None

            # --- Location ---
            try:
                location_parts = await card.locator(
                    "div.companyLocation *, div[data-testid='text-location'] *"
                ).all_text_contents()
                location = " ".join(p.strip() for p in location_parts if p.strip())
            except Exception:
                location = ""

            # --- Salary ---
            try:
                salary_parts = await card.locator(
                    "div[id='salaryInfoAndJobType'] span, "
                    "div[data-testid='attribute_snippet_text'], "
                    "div[data-testid='jobsearch-OtherJobDetailsContainer'] span, "
                    "div[data-testid='salary-snippet-container'] span, "
                    "span.css-1oc7tea, "
                    "span[data-testid='attribute_snippet_text']"
                ).all_text_contents()
                salary = " ".join(p.strip() for p in salary_parts if p.strip()) or "Not disclosed"
            except Exception:
                salary = "Not disclosed"

            # --- Job URL ---
            link_el = await card.query_selector("a")
            job_url = await link_el.get_attribute("href") if link_el else None

            if not job_url:
                continue
            if job_url.startswith("/pagead/clk"):
                print(f"⛔ Skipping ad URL: {job_url}")
                continue
            elif job_url.startswith("/"):
                job_url = urljoin("https://www.indeed.com", job_url)

            if job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            # --- Save Valid Job ---
            if title and company and job_url:
                job_data = {
                    "url": job_url,
                    "title": (title or "").strip(),
                    "company": (company or "").strip(),
                    "location": (location or "").strip(),
                    "description": f"Salary: {salary}",
                }
                print("📝 Scraped job:", job_data["title"], "-", job_data["company"])
                await upsert_job(job_data)

        print(f"📌 Total jobs scraped: {len(seen_urls)}")
        print("🎉 Jobs scraped and saved successfully!")

    except Exception as e:
        print("❌ Error during scraping:", str(e))

    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

    print("✅ Scraping completed — check jobs.db for results.")

if __name__ == "__main__":
    asyncio.run(run())
