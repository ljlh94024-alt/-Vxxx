from typing import Optional
from playwright.sync_api import Page
from worker import BaseWorker, GeminiWorker


class WorkerFactory:
    """
    Factory for creating Web AI Worker instances.
    Enables future extensions (ChatGPT, Claude, local models) without modifying Controller logic.
    """

    @staticmethod
    def create_worker(worker_type: str, page: Page, selector_file: Optional[str] = None) -> BaseWorker:
        w_type = (worker_type or "gemini").lower()
        if w_type in ("gemini", "gemini-web"):
            sel_file = selector_file or "selectors/gemini.yaml"
            return GeminiWorker(page=page, selector_file=sel_file)
        # Future workers can be hooked here:
        # elif w_type == "chatgpt":
        #     return ChatGPTWorker(page=page, selector_file=selector_file or "selectors/chatgpt.yaml")
        # elif w_type == "claude":
        #     return ClaudeWorker(page=page, selector_file=selector_file or "selectors/claude.yaml")
        else:
            raise ValueError(f"Unsupported worker type: {worker_type}")
