import os
import threading
from copy import deepcopy
from datetime import datetime
from typing import Optional, Tuple
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Playwright, BrowserContext, Page


class BrowserManager:
    """
    Browser Manager for v0.2.1 Runtime.
    Maintains persistent browser context, performs health checks, crash recovery,
    and supports continuous multi-task execution without shutdown.
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
        self._traffic_lock = threading.Lock()
        self._gemini_traffic = self._empty_traffic_stats()

    @staticmethod
    def _empty_traffic_stats():
        return {
            "request_count": 0,
            "estimated_outbound_bytes": 0,
            "response_count": 0,
            "declared_inbound_bytes": 0,
            "methods": {},
            "by_host": {},
        }

    @staticmethod
    def _is_gemini_traffic_host(host: str) -> bool:
        host = (host or "").lower().rstrip(".")
        return (
            host == "gemini.google.com"
            or host.endswith(".gemini.google.com")
            or "alkalimakersuite" in host
        )

    @staticmethod
    def _estimate_request_bytes(request) -> int:
        """Estimate clear-text HTTP request bytes; excludes TLS/HTTP2 overhead."""
        try:
            headers = request.headers
        except Exception:
            headers = {}
        header_bytes = sum(
            len(str(name).encode("utf-8")) + len(str(value).encode("utf-8")) + 4
            for name, value in headers.items()
        )
        try:
            body = request.post_data_buffer or b""
        except Exception:
            body = b""
        return (
            len(str(request.method).encode("utf-8"))
            + len(str(request.url).encode("utf-8"))
            + header_bytes
            + len(body)
            + 12
        )

    def _on_request(self, request) -> None:
        host = (urlparse(request.url).hostname or "").lower()
        if not self._is_gemini_traffic_host(host):
            return
        method = str(request.method).upper()
        size = self._estimate_request_bytes(request)
        with self._traffic_lock:
            self._gemini_traffic["request_count"] += 1
            self._gemini_traffic["estimated_outbound_bytes"] += size
            methods = self._gemini_traffic["methods"]
            methods[method] = methods.get(method, 0) + 1
            host_stats = self._gemini_traffic["by_host"].setdefault(
                host,
                {"request_count": 0, "estimated_outbound_bytes": 0,
                 "response_count": 0, "declared_inbound_bytes": 0},
            )
            host_stats["request_count"] += 1
            host_stats["estimated_outbound_bytes"] += size

    def _on_response(self, response) -> None:
        host = (urlparse(response.url).hostname or "").lower()
        if not self._is_gemini_traffic_host(host):
            return
        try:
            declared_bytes = int(response.headers.get("content-length", "0"))
        except (TypeError, ValueError):
            declared_bytes = 0
        with self._traffic_lock:
            self._gemini_traffic["response_count"] += 1
            self._gemini_traffic["declared_inbound_bytes"] += declared_bytes
            host_stats = self._gemini_traffic["by_host"].setdefault(
                host,
                {"request_count": 0, "estimated_outbound_bytes": 0,
                 "response_count": 0, "declared_inbound_bytes": 0},
            )
            host_stats["response_count"] += 1
            host_stats["declared_inbound_bytes"] += declared_bytes

    def get_gemini_traffic_snapshot(self):
        """Return sanitized cumulative counters; never includes URLs or payloads."""
        with self._traffic_lock:
            return deepcopy(self._gemini_traffic)

    def health_check(self) -> Tuple[bool, str]:
        """
        Check if browser context and page are alive, not closed, and responsive.
        Returns: (is_healthy, message)
        """
        if not self.is_running:
            return False, "Browser is not marked as running"
        if not self._context:
            return False, "Browser context is None"
        if not self._page or self._page.is_closed():
            return False, "Target page is None or closed"

        try:
            # Perform a lightweight responsive check
            title = self._page.title()
            return True, f"Browser is healthy, page title: {title}"
        except Exception as e:
            return False, f"Page health check failed: {str(e)}"

    def start(self) -> Tuple[bool, str]:
        """Start persistent context with Chromium, preserving session/cookies."""
        try:
            healthy, _ = self.health_check()
            if healthy:
                return True, "Browser already running and healthy"

            # Dispose stale Playwright/context handles before relaunching. This
            # is required when the page or browser was closed outside the
            # controller; otherwise the persistent profile can remain locked.
            if self._context is not None or self._playwright is not None:
                self.close()

            if not os.path.exists(self.profile_path):
                os.makedirs(self.profile_path, exist_ok=True)

            self._playwright = sync_playwright().start()
            browser_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=9222",
            ]
            try:
                self._context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self.profile_path,
                    headless=self.headless,
                    channel="chrome",
                    args=browser_args,
                    viewport={"width": 1280, "height": 800},
                )
            except Exception:
                self._context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self.profile_path,
                    headless=self.headless,
                    args=browser_args,
                    viewport={"width": 1280, "height": 800},
                )

            self._context.set_default_timeout(self.timeout)
            self._context.on("request", self._on_request)
            self._context.on("response", self._on_response)
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


# Backwards compatibility alias
BrowserEngine = BrowserManager
