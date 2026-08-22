import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
import yaml
from playwright.sync_api import Page, Locator


class BaseWorker(ABC):
    """
    Abstract Base Worker for web AI models.
    Defines the unified interaction contract for GeminiWorker, ChatGPTWorker, ClaudeWorker, etc.
    """

    def __init__(self, page: Page, model_name: str = "base-worker"):
        self.page = page
        self.model_name = model_name

    @abstractmethod
    def send_prompt(self, prompt: str) -> Tuple[bool, str]:
        """Send prompt to the AI model interface."""
        pass

    @abstractmethod
    def wait_response(self, timeout_sec: int = 120) -> Tuple[bool, str]:
        """Wait for the response to finish streaming and stabilize."""
        pass

    @abstractmethod
    def get_response(self) -> Tuple[bool, str, str]:
        """Retrieve the response content text."""
        pass


def load_selectors(selector_file: str = "selectors/gemini.yaml") -> Dict[str, Any]:
    if os.path.exists(selector_file):
        with open(selector_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class GeminiWorker(BaseWorker):
    """
    Gemini implementation of BaseWorker using selector adapter configurations.
    Priority hierarchy: aria -> role -> placeholder -> text -> css.
    """

    def __init__(self, page: Page, selector_file: str = "selectors/gemini.yaml"):
        super().__init__(page, model_name="gemini-web")
        self.selectors = load_selectors(selector_file)

    def find_prompt_input(self) -> Optional[Locator]:
        input_cfg = self.selectors.get("prompt_input", {})
        
        # 1. aria priority
        for aria_sel in input_cfg.get("aria", []):
            try:
                loc = self.page.locator(aria_sel)
                if loc.first.is_visible():
                    return loc.first
            except Exception:
                pass

        # 2. role priority
        for role_item in input_cfg.get("role", []):
            try:
                if isinstance(role_item, dict):
                    name = role_item.get("name")
                    role = role_item.get("role", "textbox")
                    if name:
                        loc = self.page.get_by_role(role, name=name)
                    else:
                        loc = self.page.get_by_role(role)
                    if loc.first.is_visible():
                        return loc.first
            except Exception:
                pass

        # 3. placeholder priority
        for ph_sel in input_cfg.get("placeholder", []):
            try:
                loc = self.page.locator(ph_sel)
                if loc.first.is_visible():
                    return loc.first
            except Exception:
                pass

        # 4. css priority
        for css_sel in input_cfg.get("css", []):
            try:
                loc = self.page.locator(css_sel)
                if loc.first.is_visible():
                    return loc.first
            except Exception:
                pass

        # Built-in fallbacks
        try:
            tb = self.page.get_by_role("textbox")
            if tb.first.is_visible():
                return tb.first
        except Exception:
            pass

        return None

    def find_send_button(self) -> Optional[Locator]:
        btn_cfg = self.selectors.get("send_button", {})

        # 1. aria
        for aria_sel in btn_cfg.get("aria", []):
            try:
                loc = self.page.locator(aria_sel)
                if loc.first.is_visible():
                    return loc.first
            except Exception:
                pass

        # 2. role
        for role_item in btn_cfg.get("role", []):
            try:
                if isinstance(role_item, dict):
                    name = role_item.get("name")
                    role = role_item.get("role", "button")
                    loc = self.page.get_by_role(role, name=name) if name else self.page.get_by_role(role)
                    if loc.first.is_visible():
                        return loc.first
            except Exception:
                pass

        # 3. css
        for css_sel in btn_cfg.get("css", []):
            try:
                loc = self.page.locator(css_sel)
                if loc.first.is_visible():
                    return loc.first
            except Exception:
                pass

        return None

    def send_prompt(self, prompt_text: str) -> Tuple[bool, str]:
        try:
            input_el = self.find_prompt_input()
            if not input_el:
                return False, "Could not find prompt input element on page"

            input_el.click()
            self.page.wait_for_timeout(300)

            try:
                input_el.fill(prompt_text)
            except Exception:
                input_el.press("Control+A")
                input_el.press("Backspace")
                input_el.type(prompt_text, delay=10)

            self.page.wait_for_timeout(400)

            send_btn = self.find_send_button()
            if send_btn and send_btn.is_enabled():
                send_btn.click()
            else:
                input_el.press("Enter")

            return True, ""
        except Exception as e:
            return False, f"Failed to send prompt: {str(e)}"

    def wait_response(self, timeout_sec: int = 120) -> Tuple[bool, str]:
        start_time = time.time()
        self.page.wait_for_timeout(1500)

        last_text = ""
        stable_count = 0

        stop_cfg = self.selectors.get("stop_button", {})
        stop_selectors = stop_cfg.get("aria", ["button[aria-label*='Stop' i]", "button[aria-label*='停止' i]"])

        while (time.time() - start_time) < timeout_sec:
            is_generating = False
            for s_sel in stop_selectors:
                try:
                    if self.page.locator(s_sel).first.is_visible():
                        is_generating = True
                        break
                except Exception:
                    pass

            if not is_generating:
                current_text = self.get_latest_response_text()
                if current_text and current_text == last_text:
                    stable_count += 1
                    if stable_count >= 3:
                        return True, ""
                else:
                    stable_count = 0
                    last_text = current_text

            self.page.wait_for_timeout(500)

        return False, f"Timed out waiting for Gemini response after {timeout_sec}s"

    def get_latest_response_text(self) -> str:
        try:
            resp_cfg = self.selectors.get("response_container", {})
            response_selectors = resp_cfg.get("css", [
                "message-content",
                "div.model-response-text",
                "div.response-container-content",
                "div[data-test-id='model-response-text']",
                ".markdown",
                "article",
            ])
            for sel in response_selectors:
                locators = self.page.locator(sel)
                count = locators.count()
                if count > 0:
                    last_el = locators.nth(count - 1)
                    text = last_el.inner_text().strip()
                    if text:
                        return text
            return ""
        except Exception:
            return ""

    def get_response(self) -> Tuple[bool, str, str]:
        text = self.get_latest_response_text()
        if not text:
            return False, "", "Unable to find or read response content from page"
        return True, text, ""
