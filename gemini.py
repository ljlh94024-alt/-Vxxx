import time
from typing import Optional, Tuple
from playwright.sync_api import Page, Locator


class GeminiClient:
    """
    Handles web-based interactions with the Gemini user interface.
    Adheres strictly to selector hierarchy: aria-label > role > placeholder > text > css.
    """

    def __init__(self, page: Page):
        self.page = page

    def find_prompt_input(self) -> Optional[Locator]:
        """Locate the Gemini prompt input element using priority selectors."""
        # 1. aria-label priority
        aria_locators = [
            self.page.locator("div[aria-label*='Enter a prompt' i]"),
            self.page.locator("div[aria-label*='输入提示' i]"),
            self.page.locator("div[aria-label*='prompt' i]"),
        ]
        for loc in aria_locators:
            try:
                if loc.first.is_visible():
                    return loc.first
            except Exception:
                pass

        # 2. role priority
        try:
            role_loc = self.page.get_by_role("textbox", name="Enter a prompt")
            if role_loc.first.is_visible():
                return role_loc.first
        except Exception:
            pass

        try:
            textbox = self.page.get_by_role("textbox")
            if textbox.first.is_visible():
                return textbox.first
        except Exception:
            pass

        # 3. placeholder priority
        try:
            ph_loc = self.page.locator("[placeholder*='Ask Gemini' i], [placeholder*='Enter a prompt' i]")
            if ph_loc.first.is_visible():
                return ph_loc.first
        except Exception:
            pass

        # 4. css / contenteditable fallback
        css_locators = [
            self.page.locator("div.ql-editor"),
            self.page.locator("div[contenteditable='true']"),
            self.page.locator("textarea"),
        ]
        for loc in css_locators:
            try:
                if loc.first.is_visible():
                    return loc.first
            except Exception:
                pass

        return None

    def find_send_button(self) -> Optional[Locator]:
        """Locate the send / submit button."""
        # 1. aria-label priority
        aria_locators = [
            self.page.locator("button[aria-label*='Send message' i]"),
            self.page.locator("button[aria-label*='Submit' i]"),
            self.page.locator("button[aria-label*='发送' i]"),
        ]
        for loc in aria_locators:
            try:
                if loc.first.is_visible():
                    return loc.first
            except Exception:
                pass

        # 2. role priority
        try:
            send_btn = self.page.get_by_role("button", name="Send message")
            if send_btn.first.is_visible():
                return send_btn.first
        except Exception:
            pass

        # 3. css selector
        try:
            btn = self.page.locator("button.send-button, mat-icon[data-mat-icon-name='send']")
            if btn.first.is_visible():
                return btn.first
        except Exception:
            pass

        return None

    def send_prompt(self, prompt_text: str) -> Tuple[bool, str]:
        """Focus input, fill prompt text, and trigger submission."""
        try:
            input_el = self.find_prompt_input()
            if not input_el:
                return False, "Could not find prompt input element on page"

            input_el.click()
            self.page.wait_for_timeout(300)

            # Clear and type text
            # For rich-text editors (contenteditable / Quill), fill or type
            try:
                input_el.fill(prompt_text)
            except Exception:
                # Fallback to key typing if fill is not supported on contenteditable div
                input_el.press("Control+A")
                input_el.press("Backspace")
                input_el.type(prompt_text, delay=10)

            self.page.wait_for_timeout(400)

            # Attempt sending via send button or Enter key
            send_btn = self.find_send_button()
            if send_btn and send_btn.is_enabled():
                send_btn.click()
            else:
                input_el.press("Enter")

            return True, ""
        except Exception as e:
            return False, f"Failed to send prompt: {str(e)}"

    def wait_response(self, timeout_sec: int = 120) -> Tuple[bool, str]:
        """
        Dynamically monitor page for response completion.
        Polls until streaming/generating indicators disappear and text stabilizes.
        """
        start_time = time.time()
        self.page.wait_for_timeout(1500)  # Initial grace period for request to register

        last_text = ""
        stable_count = 0

        while (time.time() - start_time) < timeout_sec:
            # Check for Stop generating / pause button indicators
            stop_btn = self.page.locator("button[aria-label*='Stop' i], button[aria-label*='停止' i]")
            is_generating = False
            try:
                if stop_btn.first.is_visible():
                    is_generating = True
            except Exception:
                pass

            if not is_generating:
                # Check current response text stability
                current_text = self.get_latest_response_text()
                if current_text and current_text == last_text:
                    stable_count += 1
                    if stable_count >= 3:  # Text unchanged for ~1.5s while not generating
                        return True, ""
                else:
                    stable_count = 0
                    last_text = current_text

            self.page.wait_for_timeout(500)

        return False, f"Timed out waiting for Gemini response after {timeout_sec}s"

    def get_latest_response_text(self) -> str:
        """Extract text from the latest response message container."""
        try:
            # Look for response message elements
            # Priority: model-response containers / structured markdown blocks
            response_selectors = [
                "message-content",
                "div.model-response-text",
                "div.response-container-content",
                "div[data-test-id='model-response-text']",
                ".markdown",
            ]
            for sel in response_selectors:
                locators = self.page.locator(sel)
                count = locators.count()
                if count > 0:
                    last_el = locators.nth(count - 1)
                    text = last_el.inner_text().strip()
                    if text:
                        return text

            # Fallback: find standard article / message blocks
            articles = self.page.locator("article")
            if articles.count() > 0:
                last_article = articles.nth(articles.count() - 1)
                text = last_article.inner_text().strip()
                if text:
                    return text

            return ""
        except Exception:
            return ""

    def get_response(self) -> Tuple[bool, str, str]:
        """
        Get the final text response from Gemini.
        Returns: (success, text_content, error_msg)
        """
        text = self.get_latest_response_text()
        if not text:
            return False, "", "Unable to find or read response content from page"
        return True, text, ""
