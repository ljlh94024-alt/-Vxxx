import queue
import time
import threading
from typing import Optional, Callable
from config import AppConfig
from task import Task, Result
from controller import Controller


class Runtime:
    """
    Continuous Runtime loop for Gemini Browser Client v0.2.1.
    Maintains persistent browser worker session, accepts tasks via queue or direct submission,
    and runs continuously without shutting down the browser between tasks.
    """

    def __init__(self, config: AppConfig, worker_id: str = "worker_0"):
        self.config = config
        self.worker_id = worker_id
        self.controller = Controller(config=config, worker_id=worker_id)
        self.task_queue: queue.Queue = queue.Queue()
        self.is_running: bool = False
        self._loop_thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Initialize runtime environment, start browser and navigate to web client."""
        started, msg = self.controller.browser_manager.start()
        if not started:
            return False
        opened, _ = self.controller.browser_manager.open_page(self.config.gemini.url)
        self.is_running = True
        return opened

    def submit_task(self, task: Task) -> Result:
        """Submit a single task directly and get the result synchronously."""
        return self.controller.execute_task(task, keep_browser_open=True)

    def enqueue_task(self, task: Task, callback: Optional[Callable[[Result], None]] = None) -> None:
        """Enqueue task for background processing."""
        self.task_queue.put((task, callback))

    def run_loop(self, poll_interval: float = 0.5) -> None:
        """Main execution loop for continuous background task processing."""
        self.is_running = True
        while self.is_running:
            try:
                item = self.task_queue.get(timeout=poll_interval)
                if item is None:
                    break
                task, callback = item
                result = self.controller.execute_task(task, keep_browser_open=True)
                if callback:
                    try:
                        callback(result)
                    except Exception:
                        pass
                self.task_queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass

    def start_background_loop(self) -> None:
        """Start the runtime loop in a background thread."""
        self._loop_thread = threading.Thread(target=self.run_loop, daemon=True)
        self._loop_thread.start()

    def shutdown(self) -> None:
        """Shutdown the runtime loop and clean up browser resources."""
        self.is_running = False
        self.task_queue.put(None)
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=3.0)
        self.controller.shutdown()
