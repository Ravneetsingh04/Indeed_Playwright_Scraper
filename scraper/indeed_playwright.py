"""
indeed_playwright.py
Pure Playwright scraper for Indeed (no ScraperAPI).

- Mirrors the structure of weworkremotely_playwright.py
- Uses the same HTML selectors and fallback logic from your Scrapy spider
- Saves results directly into jobs.db
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from urllib.parse import urljoin, urlencode
import time
import random
import logging
from datetime import datetime
import os
import sqlite3

# --- Config ---
BASE = "https://www.indeed.com"
SEARCH_QUERY = "Python Developer"
LOCATION = "New York, NY"
LISTING_PATH = f"/jobs?{urlencode({'q': SEARCH_QUERY, 'l': LOCATION, 'fromage': 1})}"
USER_AGENT = os.getenv(
    "INDEED_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MAX_PAGES = int(os.getenv("MAX_PAGES", "3"))
DOWNLOAD_DELAY = float(os.getenv("DOWNLOAD_DELAY", "1.5"))
DEFAULT_TIMEOUT = 12000  # ms
DB_PATH = os.getenv("JOBS_DB_PATH", "jobs.db")

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def random_sleep(min_s=0.5, max_s=1.0):
    time.sleep(random.uniform(min_s, max_s))


class IndeedPlaywright:
    def __init__(self, headless=True):
        self.headless = headless
        self.page_count = 0
        self.visited_pages = set()
        self.seen_urls = set()
        self.conn = self.ensure_db()

    # -------------------- Database Setup -------------------- #
    def ensure_db(self):
        conn = sqlite3.connect(DB_PATH)
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

    def upsert_job(self, job):
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                INSERT OR IGNORE INTO jobs
                (source, title, company, location, posted, salary, url, snippet, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "indeed",
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                    job.get("posted", ""),
                    job.get("salary", ""),
                    job.get("url", ""),
                    "",
                    datetime.utcnow().isoformat(),
                ),
            )
            self.conn.commit()
        except Exception as e:
            logging.warning("DB insert failed for %s: %s", job.get("url"), e)

    # -------------------- Browser Setup -------------------- #
    def start_browser(self):
        self._p = sync_playwright().start()
        self._browser = self._p.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(user_agent=USER_AGENT)
        self._page = self._context.new_page()
        self._page.set_default_timeout(DEFAULT_TIMEOUT)
        logging.info("Browser started (headless=%s)", self.headless)
        return self._page

    def close_browser(self):
        try:
            self._browser.close()
        except Exception:
            pass
        try:
            self._p.stop()
        except Exception:
            pass
        self.conn.close()
        logging.info("Browser closed and DB connection closed")

    # -------------------- Navigation -------------------- #
    def make_request(self, url):
        if self.page_count >= MAX_PAGES:
            logging.info("Max pages reached (%d). Stopping.", MAX_PAGES)
            return False

        logging.info("Visiting page #%d: %s", self.page_count + 1, url)
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=45000)
    
            # Simulate real interaction
            self._page.mouse.move(300, 300)
            self._page.keyboard.press("PageDown")
            self._page.evaluate("window.scrollBy(0, document.body.scrollHeight/2)")
            time.sleep(3)
            self._page.keyboard.press("ArrowDown")
            time.sleep(2)
            self._page.keyboard.press("ArrowDown")
    
            # Broaden our selector to anything that looks like a job card
            possible_selectors = [
                "div.job_seen_beacon",
                "a.tapItem",
                "div.slider_container",
                "div.jobsearch-SerpJobCard",
            ]
            found = False
            for sel in possible_selectors:
                try:
                    self._page.wait_for_selector(sel, timeout=8000)
                    found = True
                    break
                except PlaywrightTimeout:
                    continue
    
            if not found:
                logging.warning("⚠️ Still no job cards visible after full scroll.")
                snapshot = self._page.content()
                logging.debug("Page snapshot:\n%s", snapshot[:1000])
                return False
    
            self.page_count += 1
            self.visited_pages.add(url)
            return True
    
        except PlaywrightTimeout:
            logging.warning("Timeout visiting %s", url)
            return False
        except Exception as e:
            logging.warning("Error visiting %s: %s", url, e)
            return False

    # -------------------- Extract and Parse -------------------- #
    def extract_job_cards(self):
        sel = "div.job_seen_beacon, a.tapItem"
        nodes = self._page.query_selector_all(sel)
        logging.info("Found %d job cards", len(nodes))
        return nodes

    def parse_job_card(self, node):
        try:
            # Title
            title_el = node.query_selector("h2.jobTitle span, h2 span, a[aria-label]")
            title = title_el.inner_text().strip() if title_el else ""

            # Company
            company_el = node.query_selector("span.companyName, span[data-testid='company-name']")
            company = company_el.inner_text().strip() if company_el else ""

            # Location (can have multiple text parts)
            location_parts = []
            loc_nodes = node.query_selector_all("div.companyLocation *, div[data-testid='text-location'] *")
            for loc in loc_nodes:
                txt = loc.inner_text().strip()
                if txt:
                    location_parts.append(txt)
            location = " ".join(location_parts)

            # Salary (primary set)
            salary_parts = []
            salary_nodes = node.query_selector_all(
                "div[id='salaryInfoAndJobType'] span, "
                "div[data-testid='attribute_snippet_text'], "
                "div[data-testid='jobsearch-OtherJobDetailsContainer'] span, "
                "div[data-testid='salary-snippet-container'] span, "
                "span.css-1oc7tea, "
                "span[data-testid='attribute_snippet_text']"
            )
            for s in salary_nodes:
                txt = s.inner_text().strip()
                if txt:
                    salary_parts.append(txt)
            salary = " ".join(salary_parts)

            # Fallback salary extraction
            if not salary:
                # try to find visible text with $ or 'year' or 'hour'
                text_content = node.inner_text()
                for keyword in ["$", "hour", "year"]:
                    if keyword in text_content:
                        salary = keyword
                        break

            if not salary:
                salary = "Not disclosed"

            # URL
            link_el = node.query_selector("a")
            job_url = link_el.get_attribute("href") if link_el else None
            if not job_url:
                return None

            if job_url.startswith("/pagead/clk"):
                logging.debug("Skipping ad URL: %s", job_url)
                return None
            elif job_url.startswith("/"):
                job_url = urljoin(BASE, job_url)

            if job_url in self.seen_urls:
                return None
            self.seen_urls.add(job_url)

            job = {
                "title": title,
                "company": company,
                "location": location,
                "salary": salary,
                "posted": datetime.now().strftime("%Y-%m-%d"),
                "url": job_url,
            }

            self.upsert_job(job)
            logging.info("📝 Saved: %s - %s", job["title"], job["company"])
            return job
        except Exception as e:
            logging.debug("parse_job_card error: %s", e)
            return None

    def parse_listing_page(self):
        nodes = self.extract_job_cards()
        items_scraped = 0
        for node in nodes:
            job = self.parse_job_card(node)
            if not job:
                continue
            items_scraped += 1
            random_sleep(0.3, 0.8)
        logging.info("Items scraped from page: %d", items_scraped)
        return items_scraped

    # -------------------- Pagination -------------------- #
    def find_next_page(self):
        try:
            next_btn = self._page.query_selector("a[aria-label='Next'], a[rel='next']")
            if not next_btn:
                return None
            href = next_btn.get_attribute("href") or ""
            if not href:
                return None
            next_url = urljoin(BASE, href)
            if next_url in self.visited_pages:
                return None
            return next_url
        except Exception:
            return None

    # -------------------- Main runner -------------------- #
    def run(self, headless=True, start_path=LISTING_PATH):
        self.start_browser()
        try:
            start_url = urljoin(BASE, start_path)
            current = start_url

            ok = self.make_request(current)
            if not ok:
                logging.error("Failed to fetch start page: %s", current)
                return []

            while True:
                self.parse_listing_page()

                if self.page_count >= MAX_PAGES:
                    logging.info("Reached MAX_PAGES (%d). Stopping pagination.", MAX_PAGES)
                    break

                next_url = self.find_next_page()
                if not next_url:
                    logging.info("No next page found. Ending.")
                    break

                ok = self.make_request(next_url)
                if not ok:
                    break

                time.sleep(DOWNLOAD_DELAY)

            logging.info("✅ Crawl finished: pages=%d, jobs=%d", self.page_count, len(self.seen_urls))
        finally:
            self.close_browser()
        return []


# Run directly
if __name__ == "__main__":
    crawler = IndeedPlaywright(headless=True)
    crawler.run()
