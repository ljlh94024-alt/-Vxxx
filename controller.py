import os
from datetime import datetime
from typing import Optional

from config import AppConfig
from logger import setup_logger, log_event
from task import Task, Result
from browser import BrowserEngine
from gemini import GeminiClient
from parser import parse_response
from validator import validate_result


class State:
    INIT = "INIT"
    BROWSER_STARTING = "BROWSER_STARTING"
    BROWSER_READY = "BROWSER_READY"
    OPEN_PAGE = "OPEN_PAGE"
    CHECK_LOGIN = "CHECK_LOGIN"
    READY = "READY"
    SEND_PROMPT = "SEND_PROMPT"
    WAIT_RESPONSE = "WAIT_RESPONSE"
    READ_RESPONSE = "READ_RESPONSE"
    PARSING = "PARSING"
    VALIDATING = "VALIDATING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Controller:
    """
    Orchestrates the browser automation, task execution, retry mechanism,
    and state transitions. The Controller is the sole decision maker.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.logger = setup_logger()
        self.browser_engine = BrowserEngine(
            profile_path=config.browser.profile_path,
            headless=config.browser.headless,
            timeout=config.browser.timeout,
        )
        self.current_state = State.INIT

    def set_state(self, new_state: str, task_id: str, action: str, result: str = "", error: str = ""):
        self.current_state = new_state
        log_event(self.logger, task_id, new_state, action, result, error)

    def generate_prompt_for_attempt(self, task: Task, attempt: int, last_error: str = "") -> str:
        """
        Progressive prompt tuning according to frozen specifications:
        - Attempt 1: Raw request formatted with goal and requirements.
        - Attempt 2: Appends format reminder / error feedback.
        - Attempt 3: Strict JSON-only constraint.
        """
        base_prompt = f"请帮助我完成以下任务：\n{task.goal}\n\n要求：\n{task.prompt}\n"
        if task.expected_output:
            base_prompt += f"\n期望输出格式结构：\n{task.expected_output}\n"

        if attempt == 1:
            return base_prompt + "\n请只返回JSON，不要添加任何额外的解释说明。"
        elif attempt == 2:
            return (
                f"{base_prompt}\n"
                f"【注意：上一次回复格式校验未通过，原因：{last_error}】\n"
                "请严格按照JSON格式输出，确保包含所有必要字段，不要使用额外的Markdown包裹或闲聊文字。"
            )
        else:
            return (
                f"{base_prompt}\n"
                "【严格要求：最终尝试】请直接输出纯合法的JSON文本，以 '{' 开头并以 '}' 结尾，绝对禁止任何前后缀文本。"
            )

    def execute_task(self, task: Task) -> Result:
        """Execute task through full lifecycle and state machine."""
        task_id = task.id or "default_task"
        self.set_state(State.INIT, task_id, "start_task_execution")

        # 1. Start browser
        self.set_state(State.BROWSER_STARTING, task_id, "launch_browser")
        started, err_msg = self.browser_engine.start()
        if not started:
            self.set_state(State.FAILED, task_id, "launch_browser", error=err_msg)
            return Result(
                id=task_id,
                status="failed",
                error=f"Browser launch failure: {err_msg}",
            )
        self.set_state(State.BROWSER_READY, task_id, "launch_browser", result="Browser ready")

        try:
            # 2. Open Gemini Page
            self.set_state(State.OPEN_PAGE, task_id, f"open_{self.config.gemini.url}")
            opened, open_err = self.browser_engine.open_page(self.config.gemini.url)
            if not opened:
                screenshot_file = self.browser_engine.screenshot()
                self.set_state(State.FAILED, task_id, "open_gemini_page", error=open_err)
                return Result(
                    id=task_id,
                    status="failed",
                    error=f"Failed to navigate to Gemini: {open_err}",
                    screenshot=screenshot_file,
                )

            # 3. Check login status
            self.set_state(State.CHECK_LOGIN, task_id, "verify_authentication")
            is_logged_in, login_msg = self.browser_engine.check_login()
            if not is_logged_in:
                screenshot_file = self.browser_engine.screenshot()
                self.set_state(State.FAILED, task_id, "check_login", error=login_msg)
                return Result(
                    id=task_id,
                    status="login_required",
                    error=f"Manual authentication required in profile: {login_msg}",
                    screenshot=screenshot_file,
                )
            self.set_state(State.READY, task_id, "verify_authentication", result="Authenticated and ready")

            page = self.browser_engine.get_page()
            if not page:
                return Result(id=task_id, status="failed", error="Browser page reference lost")

            gemini_client = GeminiClient(page)
            max_retries = min(task.retry or self.config.retry.max_retry, 3)
            last_error = ""
            last_raw_content = ""

            for attempt in range(1, max_retries + 1):
                attempt_prompt = self.generate_prompt_for_attempt(task, attempt, last_error)

                # Send prompt
                self.set_state(State.SEND_PROMPT, task_id, f"send_prompt_attempt_{attempt}")
                sent, send_err = gemini_client.send_prompt(attempt_prompt)
                if not sent:
                    last_error = f"Send failed: {send_err}"
                    self.set_state(State.FAILED, task_id, "send_prompt", error=last_error)
                    continue

                # Wait response
                self.set_state(State.WAIT_RESPONSE, task_id, f"wait_response_attempt_{attempt}")
                wait_ok, wait_err = gemini_client.wait_response(timeout_sec=task.timeout or self.config.task.timeout)
                if not wait_ok:
                    last_error = f"Wait response timeout: {wait_err}"
                    self.set_state(State.FAILED, task_id, "wait_response", error=last_error)
                    continue

                # Read response
                self.set_state(State.READ_RESPONSE, task_id, f"read_response_attempt_{attempt}")
                read_ok, raw_text, read_err = gemini_client.get_response()
                if not read_ok:
                    last_error = f"Read response failed: {read_err}"
                    self.set_state(State.FAILED, task_id, "read_response", error=last_error)
                    continue

                last_raw_content = raw_text

                # Parse response
                self.set_state(State.PARSING, task_id, f"parse_attempt_{attempt}")
                parse_ok, json_dict, parse_err = parse_response(raw_text)
                if not parse_ok:
                    last_error = f"Parse failed: {parse_err}"
                    self.set_state(State.FAILED, task_id, "parse_response", error=last_error)
                    continue

                # Validate response
                self.set_state(State.VALIDATING, task_id, f"validate_attempt_{attempt}")
                val_ok, val_err = validate_result(json_dict, task.expected_output)
                if not val_ok:
                    last_error = f"Validation failed: {val_err}"
                    self.set_state(State.FAILED, task_id, "validate_result", error=last_error)
                    continue

                # Success
                self.set_state(State.SUCCESS, task_id, "task_completed_successfully")
                return Result(
                    id=task_id,
                    status="success",
                    content=last_raw_content,
                    json_result=json_dict,
                )

            # All attempts exhausted
            screenshot_file = self.browser_engine.screenshot()
            self.set_state(State.FAILED, task_id, "all_attempts_exhausted", error=last_error)
            return Result(
                id=task_id,
                status="failed",
                content=last_raw_content,
                error=f"Task execution failed after {max_retries} attempts. Last error: {last_error}",
                screenshot=screenshot_file,
            )

        finally:
            self.browser_engine.close()
