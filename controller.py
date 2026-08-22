import os
import time
import uuid
from typing import Optional, Tuple

from config import AppConfig
from logger import setup_logger, log_event
from task import Task, Result
from store import StateStore, TaskState
from browser import BrowserManager
from worker_factory import WorkerFactory
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
    RETRYING = "RETRYING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Controller:
    """
    v0.2.1 Runtime Controller.
    Responsible for worker lifecycle, state transitions, auto-recovery on browser/page crash,
    execution history recording in SQLite, and WorkerFactory integration.
    """

    def __init__(self, config: AppConfig, worker_id: str = "worker_0", db_path: str = "data/state.db"):
        self.config = config
        self.worker_id = worker_id
        self.logger = setup_logger()
        self.state_store = StateStore(db_path=db_path)
        self.browser_manager = BrowserManager(
            profile_path=config.browser.profile_path,
            headless=config.browser.headless,
            timeout=config.browser.timeout,
            browser_id=f"browser_{worker_id}",
        )
        self.current_state = State.INIT
        self.is_initialized = False

    def set_state(
        self,
        new_state: str,
        task_id: str,
        action: str,
        result: str = "",
        error: str = "",
        execution_id: str = "",
        retry_count: int = 0,
        start_time: float = 0.0,
    ) -> None:
        self.current_state = new_state
        duration = (time.time() - start_time) if start_time > 0 else 0.0
        log_event(
            logger=self.logger,
            task_id=task_id,
            state=new_state,
            action=action,
            result=result,
            error=error,
            execution_id=execution_id,
            worker_id=self.worker_id,
            browser_id=self.browser_manager.browser_id,
            retry_count=retry_count,
            duration=duration,
            model="gemini-web",
        )

    def initialize_runtime(self) -> Tuple[bool, str]:
        """Start browser once and navigate to Gemini page."""
        started, err = self.browser_manager.start()
        if not started:
            return False, f"Browser start failed: {err}"

        opened, open_err = self.browser_manager.open_page(self.config.gemini.url)
        if not opened:
            return False, f"Navigation to {self.config.gemini.url} failed: {open_err}"

        self.is_initialized = True
        return True, ""

    def generate_prompt_for_attempt(self, task: Task, attempt: int, last_error: str = "") -> str:
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

    def recover_runtime(self, task_id: str, execution_id: str) -> bool:
        """Crash recovery: restart browser manager and reload page safely."""
        self.set_state(State.RETRYING, task_id, "recover_browser_runtime", execution_id=execution_id)
        restarted, err = self.browser_manager.restart()
        if not restarted:
            return False
        opened, _ = self.browser_manager.open_page(self.config.gemini.url)
        page = self.browser_manager.get_page()
        return opened and page is not None and not page.is_closed()

    def execute_task(self, task: Task, keep_browser_open: bool = True) -> Result:
        task_id = task.id or f"task_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        # State store: Task Created
        self.state_store.create_task(task_id)
        self.state_store.update_state(task_id, TaskState.RUNNING)

        try:
            # Check or start browser with health check
            healthy, _ = self.browser_manager.health_check()
            if not healthy:
                self.set_state(State.BROWSER_STARTING, task_id, "launch_browser", start_time=start_time)
                started, err_msg = self.browser_manager.start()
                if not started:
                    self.set_state(State.FAILED, task_id, "launch_browser", error=err_msg, start_time=start_time)
                    self.state_store.update_state(task_id, TaskState.FAILED, error=err_msg)
                    return Result(id=task_id, status="failed", error=f"Browser launch failure: {err_msg}")
                self.set_state(State.BROWSER_READY, task_id, "launch_browser", result="Browser ready", start_time=start_time)

            # Open or ensure page
            self.set_state(State.OPEN_PAGE, task_id, f"open_{self.config.gemini.url}", start_time=start_time)
            opened, open_err = self.browser_manager.open_page(self.config.gemini.url)
            if not opened:
                init_exec_id = f"exec_{task_id}_init"
                recovered = self.recover_runtime(task_id, init_exec_id)
                if not recovered:
                    screenshot_file = self.browser_manager.screenshot()
                    self.set_state(State.FAILED, task_id, "open_page_failed", error=open_err, start_time=start_time)
                    self.state_store.update_state(task_id, TaskState.FAILED, error=open_err)
                    return Result(id=task_id, status="failed", error=f"Page open failed: {open_err}", screenshot=screenshot_file)

            # Check login
            self.set_state(State.CHECK_LOGIN, task_id, "verify_authentication", start_time=start_time)
            is_logged_in, login_msg = self.browser_manager.check_login()
            if not is_logged_in:
                screenshot_file = self.browser_manager.screenshot()
                self.set_state(State.FAILED, task_id, "check_login", error=login_msg, start_time=start_time)
                self.state_store.update_state(task_id, TaskState.FAILED, error=login_msg)
                return Result(id=task_id, status="login_required", error=f"Login required: {login_msg}", screenshot=screenshot_file)

            self.set_state(State.READY, task_id, "verify_authentication", result="Authenticated", start_time=start_time)

            page = self.browser_manager.get_page()
            if not page or page.is_closed():
                self.state_store.update_state(task_id, TaskState.FAILED, error="Page reference lost")
                return Result(id=task_id, status="failed", error="Page reference lost")

            worker = WorkerFactory.create_worker("gemini", page)
            max_retries = min(task.retry or self.config.retry.max_retry, 3)
            last_error = ""
            last_raw_content = ""

            for attempt in range(1, max_retries + 1):
                attempt_start = time.time()
                execution_id = f"exec_{task_id}_{attempt}"
                attempt_prompt = self.generate_prompt_for_attempt(task, attempt, last_error)

                # Send prompt
                self.set_state(State.SEND_PROMPT, task_id, f"send_prompt_attempt_{attempt}", execution_id=execution_id, retry_count=attempt, start_time=start_time)
                sent, send_err = worker.send_prompt(attempt_prompt)
                if not sent:
                    last_error = f"Send failed: {send_err}"
                    # Try recovery if page crashed
                    if "Target page, context or browser has been closed" in send_err:
                        self.recover_runtime(task_id, execution_id)
                        new_page = self.browser_manager.get_page()
                        if new_page and not new_page.is_closed():
                            worker = WorkerFactory.create_worker("gemini", new_page)
                    self.set_state(State.FAILED, task_id, "send_prompt", error=last_error, execution_id=execution_id, retry_count=attempt, start_time=start_time)
                    self.state_store.record_execution(execution_id, task_id, attempt, TaskState.FAILED, error=last_error, duration=time.time() - attempt_start)
                    self.state_store.update_state(task_id, TaskState.RETRYING, error=last_error)
                    continue

                # Wait response
                self.set_state(State.WAIT_RESPONSE, task_id, f"wait_response_attempt_{attempt}", execution_id=execution_id, retry_count=attempt, start_time=start_time)
                wait_ok, wait_err = worker.wait_response(timeout_sec=task.timeout or self.config.task.timeout)
                if not wait_ok:
                    last_error = f"Wait timeout: {wait_err}"
                    self.set_state(State.FAILED, task_id, "wait_response", error=last_error, execution_id=execution_id, retry_count=attempt, start_time=start_time)
                    self.state_store.record_execution(execution_id, task_id, attempt, TaskState.FAILED, error=last_error, duration=time.time() - attempt_start)
                    self.state_store.update_state(task_id, TaskState.RETRYING, error=last_error)
                    continue

                # Read response
                self.set_state(State.READ_RESPONSE, task_id, f"read_response_attempt_{attempt}", execution_id=execution_id, retry_count=attempt, start_time=start_time)
                read_ok, raw_text, read_err = worker.get_response()
                if not read_ok:
                    last_error = f"Read failed: {read_err}"
                    self.set_state(State.FAILED, task_id, "read_response", error=last_error, execution_id=execution_id, retry_count=attempt, start_time=start_time)
                    self.state_store.record_execution(execution_id, task_id, attempt, TaskState.FAILED, error=last_error, duration=time.time() - attempt_start)
                    self.state_store.update_state(task_id, TaskState.RETRYING, error=last_error)
                    continue

                last_raw_content = raw_text

                # Parse response
                self.set_state(State.PARSING, task_id, f"parse_attempt_{attempt}", execution_id=execution_id, retry_count=attempt, start_time=start_time)
                parse_ok, json_dict, parse_err = parse_response(raw_text)
                if not parse_ok:
                    last_error = f"Parse failed: {parse_err}"
                    self.set_state(State.FAILED, task_id, "parse_response", error=last_error, execution_id=execution_id, retry_count=attempt, start_time=start_time)
                    self.state_store.record_execution(execution_id, task_id, attempt, TaskState.FAILED, error=last_error, duration=time.time() - attempt_start)
                    self.state_store.update_state(task_id, TaskState.RETRYING, error=last_error)
                    continue

                # Validate response
                self.set_state(State.VALIDATING, task_id, f"validate_attempt_{attempt}", execution_id=execution_id, retry_count=attempt, start_time=start_time)
                val_ok, val_err = validate_result(json_dict, task.expected_output)
                if not val_ok:
                    last_error = f"Validation failed: {val_err}"
                    self.set_state(State.FAILED, task_id, "validate_result", error=last_error, execution_id=execution_id, retry_count=attempt, start_time=start_time)
                    self.state_store.record_execution(execution_id, task_id, attempt, TaskState.FAILED, error=last_error, duration=time.time() - attempt_start)
                    self.state_store.update_state(task_id, TaskState.RETRYING, error=last_error)
                    continue

                # Success
                duration = time.time() - attempt_start
                self.set_state(State.SUCCESS, task_id, "task_completed_successfully", execution_id=execution_id, retry_count=attempt, start_time=start_time)
                self.state_store.record_execution(execution_id, task_id, attempt, TaskState.SUCCESS, duration=duration)
                self.state_store.update_state(task_id, TaskState.SUCCESS, result=json_dict)
                return Result(
                    id=task_id,
                    status="success",
                    content=last_raw_content,
                    json_result=json_dict,
                )

            # All attempts failed
            screenshot_file = self.browser_manager.screenshot()
            self.set_state(State.FAILED, task_id, "all_attempts_exhausted", error=last_error, start_time=start_time)
            self.state_store.update_state(task_id, TaskState.FAILED, error=last_error)
            return Result(
                id=task_id,
                status="failed",
                content=last_raw_content,
                error=f"Task execution failed after {max_retries} attempts. Last error: {last_error}",
                screenshot=screenshot_file,
            )

        finally:
            if not keep_browser_open:
                self.browser_manager.close()

    def shutdown(self) -> None:
        """Shutdown the runtime environment."""
        self.browser_manager.close()
