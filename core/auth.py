from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from core import config
from core.session_manager import SessionManager


class AuthenticationError(Exception):
    pass


class SessionExpiredError(Exception):
    pass


class AuthManager:
    def __init__(self, session: SessionManager, credentials_path: Path = config.CREDENTIALS_PATH):
        self._session = session
        self._credentials_path = credentials_path

    # ── Credentials ───────────────────────────────────────────────────────────

    def _load_credentials(self) -> tuple[str, str]:
        """Read userpsw.txt — line 1 = username, line 2 = password."""
        lines = self._credentials_path.read_text().splitlines()
        if len(lines) < 2:
            raise AuthenticationError(
                f"userpsw.txt must have two lines (username, password). Found: {len(lines)}"
            )
        return lines[0].strip(), lines[1].strip()

    # ── Session validity ──────────────────────────────────────────────────────

    async def is_session_valid(self) -> bool:
        """
        Navigate to the app and check whether we land on a logged-in page.
        Returns False if we are redirected to the login screen.
        """
        if not config.SEL_LOGGED_IN_INDICATOR:
            # Selectors not yet configured — assume session is invalid so login runs.
            return False

        page = await self._session.get_page()
        try:
            await page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)

            # Wait for either the logged-in indicator or the login form to appear
            await page.wait_for_selector(
                f"{config.SEL_LOGGED_IN_INDICATOR}, {config.SEL_SESSION_EXPIRED}",
                timeout=config.PAGE_TIMEOUT_MS,
            )

            # If the login form is showing, session is gone
            if "SSUser.Logon" in page.url:
                return False

            indicator = await page.query_selector(config.SEL_LOGGED_IN_INDICATOR)
            return indicator is not None and await indicator.is_visible()
        except PlaywrightTimeout:
            return False

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(self) -> bool:
        """
        Perform a full login sequence. Saves cookies on success.
        Returns True on success, raises AuthenticationError on failure.
        """
        username, password = self._load_credentials()
        page = await self._session.get_page()

        login_url = config.BASE_URL + config.LOGIN_HASH
        await page.goto(login_url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)

        # Wait for the login form to render (SPA needs time after DOM is loaded)
        if config.SEL_USERNAME:
            try:
                await page.wait_for_selector(config.SEL_USERNAME, state="visible", timeout=config.PAGE_TIMEOUT_MS)
            except PlaywrightTimeout:
                # Maybe we're already logged in (cookies still valid)
                indicator = await page.query_selector(config.SEL_LOGGED_IN_INDICATOR)
                if indicator and await indicator.is_visible():
                    await self._session.save_cookies()
                    return True
                raise AuthenticationError("Login form did not appear — check SEL_USERNAME in config.py")

            await page.fill(config.SEL_USERNAME, username)
            await page.fill(config.SEL_PASSWORD, password)

            if config.SEL_LOGIN_BUTTON:
                await page.click(config.SEL_LOGIN_BUTTON)
            else:
                await page.keyboard.press("Enter")
        else:
            # Selectors not yet configured — open headed so user can log in manually
            raise AuthenticationError(
                "DOM selectors not configured. Run 'python explore.py' first to discover selectors, "
                "then fill them in core/config.py."
            )

        # Wait for successful navigation away from login page
        try:
            if config.SEL_LOGGED_IN_INDICATOR:
                await page.wait_for_selector(
                    config.SEL_LOGGED_IN_INDICATOR,
                    timeout=config.PAGE_TIMEOUT_MS,
                )
            else:
                # Fallback: wait until the URL no longer contains the login hash
                await page.wait_for_function(
                    "() => !window.location.hash.includes('SSUser.Logon')",
                    timeout=config.PAGE_TIMEOUT_MS,
                )
        except PlaywrightTimeout:
            raise AuthenticationError(
                "Login failed — still on login page after submitting credentials. "
                "Check that your username/password in userpsw.txt are correct."
            )

        await self._session.save_cookies()
        return True

    # ── High-level entry point ────────────────────────────────────────────────

    async def ensure_authenticated(self) -> bool:
        """
        Load saved cookies and validate the session. Re-login if expired.
        All ResultsManager calls should start here.
        """
        # Cookies are already loaded in SessionManager.launch(), but reload the page
        # to verify the session is still alive server-side.
        if await self.is_session_valid():
            return True

        # Session gone — attempt fresh login
        await self._session.clear_cookies()
        await self.login()
        return True


# ── Retry helper ──────────────────────────────────────────────────────────────

async def with_auth_retry(coro, auth: AuthManager, max_retries: int = 1):
    """
    Execute an awaitable. If a SessionExpiredError is raised, re-authenticate
    and retry once.

    Usage:
        result = await with_auth_retry(results_manager.search_by_specimen(sid), auth)
    """
    for attempt in range(max_retries + 1):
        try:
            return await coro
        except SessionExpiredError:
            if attempt == max_retries:
                raise
            await auth.ensure_authenticated()
