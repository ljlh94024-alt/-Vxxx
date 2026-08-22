import os
from datetime import datetime
from typing import Optional, Tuple
from playwright.sync_api import sync_playwright, Playwright, BrowserContext, Page


class BrowserManager:
    """
    Browser Manager for v0.2 Runtime.
    Maintains persistent browser context across continuous tasks, handles crashes and auto-recovery.
    """

    def __init__(
        self,
        profile_path: str = "./data/profile",
        headless: bool = False,
        timeout: int = 60,
        browser_id: str = "browser_0",
    ):
        self.profile_path = os.path.abspath(profile_path)
        self.headless = headless
        self.timeout = timeout * 1000  # Convert to ms
        self.browser_id = browser_id
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self.is_running: bool = False

    def start(self) -> Tuple[bool, str]:
        """Start persistent context with Chromium, preserving session/cookies."""
        try:
            if self.is_running and self._page and not self._page.is_closed():
                return True, "Browser already running"

            if not os.path.exists(self.profile_path):
                os.makedirs(self.profile_path, exist_ok=True)

            self._playwright = sync_playwright().start()
            try:
                self._context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self.profile_path,
                    headless=self.headless,
                    channel="chrome",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                    viewport={"width": 1280, "height": 800},
                )
            except Exception:
                self._context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self.profile_path,
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                    viewport={"width": 1280, "height": 800},
                )

            self._context.set_default_timeout(self.timeout)
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = self._context.new_page()

            self.is_running = True
            return True, ""
        except Exception as e:
            self.is_running = False
            return False, f"Failed to start browser: {str(e)}"

    def restart(self) -> Tuple[bool, str]:
        """Gracefully close and restart browser context (for recovery)."""
        self.close()
        return self.start()

    def open_page(self, url: str) -> Tuple[bool, str]:
        """Navigate to target URL, ensuring page is alive."""
        if not self._page or self._page.is_closed():
            started, err = self.start()
            if not started:
                return False, f"Cannot open page, start failed: {err}"

        try:
            assert self._page is not None
            self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
            return True, ""
        except Exception as e:
            return False, f"Failed to open {url}: {str(e)}"

    def check_login(self) -> Tuple[bool, str]:
        """Check authentication status on current page."""
        if not self._page or self._page.is_closed():
            return False, "Browser page is closed or not initialized"

        try:
            sign_in_selectors = [
                "a[aria-label*='Sign in' i]",
                "button[aria-label*='Sign in' i]",
                "a:has-text('Sign in')",
                "button:has-text('Sign in')",
                "a:has-text('登录')",
                "button:has-text('登录')",
            ]
            for sel in sign_in_selectors:
                if self._page.locator(sel).first.is_visible():
                    return False, "Login button detected; login is required"

            input_selectors = [
                "div[aria-label*='Enter a prompt' i]",
                "div[aria-label*='输入提示' i]",
                "div[role='textbox']",
                "textarea[placeholder*='prompt' i]",
                "div.ql-editor",
            ]
            for sel in input_selectors:
                if self._page.locator(sel).first.is_visible():
                    return True, "Prompt input area present; user authenticated"

            if self._page.get_by_role("textbox").first.is_visible():
                return True, "Textbox role is visible"

            return False, "No active prompt input area found; manual login may be required"
        except Exception as e:
            return False, f"Login check error: {str(e)}"

    def screenshot(self, path: Optional[str] = None) -> str:
        """Capture screenshot of the current page state."""
        if not self._page or self._page.is_closed():
            return ""
        if not path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.abspath(f"./data/screenshots/{timestamp}_error.png")

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        try:
            self._page.screenshot(path=path, full_page=True)
            return path
        except Exception:
            return ""

    def get_page(self) -> Optional[Page]:
        return self._page

    def close(self) -> None:
        """Gracefully close browser context without deleting profile directory."""
        try:
            if self._context:
                self._context.close()
                self._context = None
        except Exception:
            pass

        try:
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
        except Exception:
            pass
        self._page = None
        self.is_running = False


# Backwards compatibility alias for v0.1 BrowserEngine
BrowserEngine = BrowserManager
