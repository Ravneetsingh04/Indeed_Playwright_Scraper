# scraper/playwright_client.py
import os
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def create_stealth_context(proxy_server: str | None = None, headless: bool = True):
    """
    Launch Playwright, create a browser context + page, and apply stealth patches.
    Returns (playwright, browser, context, page) so the caller can close them when done.
    """
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=headless)
    # supply proxy_server like "http://user:pass@host:port" or None
    context = await browser.new_context(
        proxy={"server": proxy_server} if proxy_server else None,
        user_agent=(os.getenv("USER_AGENT") or
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"),
        locale="en-US",
        viewport={"width": 1366, "height": 768},
        java_script_enabled=True,
        ignore_https_errors=True
    )
    page = await context.new_page()
    # Apply stealth patches BEFORE navigation
    await stealth_async(page)
    return playwright, browser, context, page


    page = await context.new_page()
    await stealth_async(page)
    await page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
    return playwright, browser, context, page
