import os
from datetime import datetime
from typing import Optional, Tuple
from playwright.sync_api import sync_playwright, Playwright, BrowserContext, Page


class BrowserEngine:
    def __init__(self, profile_path: str = "./data/profile", headless: bool = False, timeout: int = 60):
        self.profile_path = os.path.abspath(profile_path)
        self.headless = headless
        self.timeout = timeout * 1000  # Convert to milliseconds for Playwright
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def start(self) -> Tuple[bool, str]:
        """Start persistent context with Chromium, preserving session/cookies."""
        try:
            if not os.path.exists(self.profile_path):
                os.makedirs(self.profile_path, exist_ok=True)

            self._playwright = sync_playwright().start()
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=self.profile_path,
                headless=self.headless,
                channel="chrome",  # Falls back to bundled chromium if chrome is not found or not specified
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
                viewport={"width": 1280, "height": 800},
            )
            # Default timeout for pages
            self._context.set_default_timeout(self.timeout)
            
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = self._context.new_page()

            return True, ""
        except Exception as e:
            # If channel="chrome" fails, retry without channel parameter to use bundled chromium
            try:
                if self._playwright:
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
                    return True, ""
            except Exception as inner_e:
                return False, f"Failed to start browser: {str(inner_e)}"
            return False, f"Failed to start browser: {str(e)}"

    def open_page(self, url: str) -> Tuple[bool, str]:
        """Navigate to target URL and wait for DOM content load."""
        if not self._page:
            return False, "Browser page is not initialized"
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
            return True, ""
        except Exception as e:
            return False, f"Failed to open {url}: {str(e)}"

    def check_login(self) -> Tuple[bool, str]:
        """
        Check if user is currently logged into Gemini.
        Returns: (is_logged_in, message)
        """
        if not self._page:
            return False, "Browser page not initialized"

        try:
            # Look for Sign In buttons / login triggers
            # Priority: aria-label -> role -> text
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

            # Check if input area is available (indicating authenticated readiness)
            input_selectors = [
                "div[aria-label*='Enter a prompt' i]",
                "div[aria-label*='输入提示' i]",
                "div[role='textbox']",
                "textarea[placeholder*='prompt' i]",
                "div.ql-editor",
            ]
            for sel in input_selectors:
                if self._page.locator(sel).first.is_visible():
                    return True, "Input element is present and user is logged in"

            # Check general text box role
            if self._page.get_by_role("textbox").first.is_visible():
                return True, "Textbox role is visible"

            return False, "No active prompt input area found; manual login may be required"
        except Exception as e:
            return False, f"Login check error: {str(e)}"

    def screenshot(self, path: Optional[str] = None) -> str:
        """Capture screenshot of the current page state."""
        if not self._page:
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
        """Gracefully close browser context and Playwright instance."""
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
