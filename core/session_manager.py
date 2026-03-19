import json
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from core import config


class SessionManager:
    """
    Owns the Playwright browser lifecycle and cookie persistence.
    Use as an async context manager:

        async with SessionManager() as sm:
            page = await sm.get_page()
    """

    def __init__(self, headless: bool = config.BROWSER_HEADLESS):
        self._headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "SessionManager":
        await self.launch()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def launch(self) -> BrowserContext:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        self._context.set_default_timeout(config.PAGE_TIMEOUT_MS)
        await self.load_cookies()
        return self._context

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    # ── Page access ───────────────────────────────────────────────────────────

    async def get_page(self) -> Page:
        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()
        return self._page

    # ── Cookie persistence ────────────────────────────────────────────────────

    async def save_cookies(self) -> None:
        cookies = await self._context.cookies()
        config.COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.COOKIES_PATH.write_text(json.dumps(cookies, indent=2))

    async def load_cookies(self) -> bool:
        """Load saved cookies into the browser context. Returns True if cookies existed."""
        if not config.COOKIES_PATH.exists():
            return False
        try:
            cookies = json.loads(config.COOKIES_PATH.read_text())
            if cookies:
                await self._context.add_cookies(cookies)
            return True
        except (json.JSONDecodeError, Exception):
            return False

    async def clear_cookies(self) -> None:
        """Delete saved cookies file and clear the browser context."""
        if config.COOKIES_PATH.exists():
            config.COOKIES_PATH.unlink()
        await self._context.clear_cookies()
        self._page = None
