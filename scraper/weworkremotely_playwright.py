"""
weworkremotely_playwright.py
Pure Playwright implementation for WeWorkRemotely (no ScraperAPI).

Drop into: Indeed_Playwright_Scraper/scraper/weworkremotely_playwright.py
Run:
    pip install playwright
    playwright install
    python scraper/weworkremotely_playwright.py

Behaviour:
- Mirrors your Scrapy structure: fetch listing -> parse cards -> fetch pagination
- Uses similar selectors/fields as your Scrapy example (title, company, location, posted, salary, url)
- Limits pages to MAX_PAGES to mimic MAX_API_CALLS
- Saves CSV: weworkremotely_playwright_jobs.csv
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from urllib.parse import urljoin, urlencode
import csv
import time
import random
import logging
from datetime import datetime
import os

# --- Config (customize if needed) ---
BASE = "https://weworkremotely.com"
SEARCH_QUERY = "Java Developer"
LISTING_PATH = f"/remote-jobs/search?term={SEARCH_QUERY.replace(' ', '+')}"
# &sort=Past+24+Hours
OUTPUT_CSV = "weworkremotely_playwright_jobs.csv"
USER_AGENT = os.getenv(
    "WWR_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MAX_PAGES = int(os.getenv("MAX_PAGES", "5"))      # Equivalent to MAX_API_CALLS in your Scrapy example
DOWNLOAD_DELAY = float(os.getenv("DOWNLOAD_DELAY", "1.0"))
DEFAULT_TIMEOUT = 12000  # ms for page.goto / waiting selectors

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def random_sleep(min_s=0.3, max_s=1.0):
    time.sleep(random.uniform(min_s, max_s))


class WeWorkRemotelyPlaywright:
    def __init__(self, headless=True):
        self.headless = headless
        self.page_count = 0
        self.seen_urls = set()
        self.visited_pages = set()
        self.results = []

    # def start_browser(self):
    #     self._p = sync_playwright().start()
    #     # use chromium by default (you can change to firefox if desired)
    #     self._browser = self._p.chromium.launch(headless=self.headless)
    #     self._context = self._browser.new_context(
    #         user_agent=USER_AGENT,
    #         viewport={"width": 1280, "height": 800},
    #         locale="en-US",
    #         java_script_enabled=True,
    #     )
    #     self._context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    #     self._page = self._context.new_page()
    #     # small default timeout
    #     self._page.set_default_timeout(DEFAULT_TIMEOUT)
    #     logging.info("Browser started (headless=%s)", self.headless)
    #     return self._page

    def start_browser(self):
        self._p = sync_playwright().start()
        # Launch with stealth-like settings
        self._browser = self._p.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-gpu",
                "--window-size=1280,800"
            ]
        )

        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            java_script_enabled=True,
        )
        # Remove webdriver flag to avoid detection
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

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
        logging.info("Browser closed")

    # def make_request(self, url):
    #     """
    #     Visit a page with Playwright. Equivalent of Scrapy request wrapped with internal counters.
    #     """
    #     if self.page_count >= MAX_PAGES:
    #         logging.info("Max pages reached (%d). Not requesting: %s", MAX_PAGES, url)
    #         return False

    #     logging.info("Visiting listing page #%d: %s", self.page_count + 1, url)
    #     try:
    #         for attempt in range(3):
    #             try:
    #                 self._page.goto(url, timeout=60000, wait_until="domcontentloaded")
    #                 self._page.wait_for_load_state("networkidle", timeout=30000)
    #                 break
    #             except PlaywrightTimeout:
    #                 logging.warning("Timeout while visiting %s", url)
    #                 if attempt == 2:
    #                     raise
    #                 time.sleep(3)
    #     except Exception as e:
    #         logging.warning("Error visiting %s : %s", url, e)
    #         return False

    def make_request(self, url):
        """
        Visit a page with retry and longer timeout (robust against slow WWR loads).
        """
        if self.page_count >= MAX_PAGES:
            logging.info("Max pages reached (%d). Not requesting: %s", MAX_PAGES, url)
            return False

        logging.info("Visiting listing page #%d: %s", self.page_count + 1, url)

        for attempt in range(3):  # up to 3 retries
            try:
                self._page.goto(url, timeout=90000, wait_until="domcontentloaded")
                self._page.wait_for_load_state("networkidle", timeout=45000)

                # ensure jobs are present before proceeding
                self._page.wait_for_selector("li.new-listing-container", timeout=20000)
                random_sleep(0.4, 1.0)
                self.page_count += 1
                self.visited_pages.add(url)
                logging.info("Successfully loaded page #%d", self.page_count)
                return True

            except PlaywrightTimeout:
                logging.warning(f"Timeout on attempt {attempt+1} for {url}")
                time.sleep(3)
            except Exception as e:
                logging.warning(f"Error visiting {url} (attempt {attempt+1}): {e}")
                time.sleep(2)

        logging.error("Failed to fetch page after 3 attempts: %s", url)
        return False

    def extract_job_cards(self):
        """
        Use the same listing selector you used in Scrapy:
        li.new-listing-container:not(.feature--ad)
        """
        sel = "li.new-listing-container:not(.feature--ad)"
        nodes = self._page.query_selector_all(sel)
        logging.info("Found %d job card nodes on page", len(nodes))
        return nodes

    def parse_job_card(self, node):
        """
        Parse a single ElementHandle node and return a dict similar to your Scrapy item.
        """
        try:
            href = node.query_selector("a[href^='/remote-jobs/']")
            if not href:
                # fallback: find first anchor
                a = node.query_selector("a")
                if not a:
                    return None
                href_val = a.get_attribute("href") or ""
            else:
                href_val = href.get_attribute("href") or ""

            if not href_val:
                return None

            job_url = urljoin(BASE, href_val)

            # Avoid duplicates
            if job_url in self.seen_urls:
                return None
            self.seen_urls.add(job_url)

            # Title, company, location, posted
            title = node.query_selector("h3.new-listing__header__title")
            company = node.query_selector("p.new-listing__company-name")
            location = node.query_selector("p.new-listing__company-headquarters")
            posted = node.query_selector("p.new-listing__header__icons__date")

            title_text = title.inner_text().strip() if title else ""
            company_text = company.inner_text().strip() if company else ""
            location_text = location.inner_text().strip() if location else ""
            posted_text = posted.inner_text().strip() if posted else datetime.now().strftime("%Y-%m-%d")

            # categories block may contain salary info
            categories = node.query_selector_all("div.new-listing__categories p")
            salary = "Not disclosed"
            if categories:
                for c in categories:
                    ctext = c.inner_text().strip()
                    if "$" in ctext:
                        salary = ctext
                        break

            item = {
                "title": title_text,
                "company": company_text,
                "location": location_text,
                "posted": posted_text,
                "salary": salary,
                "url": job_url,
            }
            return item
        except Exception as e:
            logging.debug("parse_job_card error: %s", e)
            return None

    def parse_listing_page(self):
        nodes = self.extract_job_cards()
        items_scraped = 0
        for node in nodes:
            item = self.parse_job_card(node)
            if not item:
                continue
            logging.info("Yielding: %s @ %s (%s)", item["title"], item["company"], item["location"])
            self.results.append(item)
            items_scraped += 1
            random_sleep(0.1, 0.5)

        logging.info("Items yielded from this page: %d", items_scraped)
        return items_scraped

    def find_next_page(self):
        """
        Mirror Scrapy selector a[rel='next']::attr(href)
        If found, return absolute url. Otherwise return None.
        """
        try:
            a = self._page.query_selector("a[rel='next']")
            if not a:
                return None
            href = a.get_attribute("href") or ""
            if not href:
                return None
            next_url = urljoin(BASE, href)
            # Avoid revisits
            if next_url in self.visited_pages:
                return None
            return next_url
        except Exception:
            return None

    # def save_to_csv(self, filename=OUTPUT_CSV):
    #     keys = ["title", "company", "location", "posted", "salary", "url"]
    #     with open(filename, "w", newline="", encoding="utf-8") as f:
    #         writer = csv.DictWriter(f, fieldnames=keys)
    #         writer.writeheader()
    #         for r in self.results:
    #             writer.writerow(r)
    #     logging.info("Saved %d records to %s", len(self.results), filename)

    def save_to_csv(self, filename=OUTPUT_CSV):
        keys = ["title", "company", "location", "posted", "salary", "url"]

        # --- Step 1: Load existing jobs (if CSV exists)
        existing_jobs = []
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_jobs.append(row)

        # --- Step 2: Avoid duplicates (compare by 'url')
        existing_urls = {job["url"] for job in existing_jobs}
        new_unique_jobs = [job for job in self.results if job["url"] not in existing_urls]

        if not new_unique_jobs:
            logging.info("No new unique jobs found — CSV not updated.")
            return

        # --- Step 3: Combine new + old (new on top)
        combined_jobs = new_unique_jobs + existing_jobs

        # --- Step 4: Write back all jobs
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(combined_jobs)

        logging.info(
            "Saved %d new jobs (total %d records now) to %s",
            len(new_unique_jobs),
            len(combined_jobs),
            filename,
        )


    def run(self, headless=True, start_path=LISTING_PATH):
        self.start_browser()
        try:
            start_url = urljoin(BASE, start_path)
            current = start_url

            # First page
            ok = self.make_request(current)
            if not ok:
                logging.error("Failed to fetch start page: %s", current)
                return self.results

            # Loop pages while not exceeding MAX_PAGES
            while True:
                self.parse_listing_page()

                if self.page_count >= MAX_PAGES:
                    logging.info("Reached MAX_PAGES (%d). Stopping pagination.", MAX_PAGES)
                    break

                next_url = self.find_next_page()
                if not next_url:
                    logging.info("No next page found. Ending pagination.")
                    break

                # visit next
                ok = self.make_request(next_url)
                if not ok:
                    logging.warning("Failed to load next page: %s", next_url)
                    break

                # polite download delay similar to Scrapy DOWNLOAD_DELAY
                time.sleep(DOWNLOAD_DELAY)

            logging.info("Crawl finished: pages=%d unique_jobs=%d", self.page_count, len(self.seen_urls))
        finally:
            self.close_browser()

        # save and return results
        self.save_to_csv()
        return self.results


# If run as script
if __name__ == "__main__":
    crawler = WeWorkRemotelyPlaywright(headless=True)
    crawler.run()
