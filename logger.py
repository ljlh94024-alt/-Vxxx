import os
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = getattr(record, "structured_data", None)
        if isinstance(data, dict):
            return json.dumps(data, ensure_ascii=False)
        return json.dumps({
            "time": datetime.now().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }, ensure_ascii=False)


def setup_logger(log_file_path: str = "data/logs/app.log") -> logging.Logger:
    logger = logging.getLogger("gemini_browser_client")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    log_dir = os.path.dirname(log_file_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(JsonFormatter())
    logger.addHandler(console_handler)

    return logger


def log_event(
    logger: logging.Logger,
    task_id: str,
    state: str,
    action: str,
    result: Optional[str] = None,
    error: Optional[str] = None,
    execution_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    browser_id: Optional[str] = None,
    retry_count: int = 0,
    duration: float = 0.0,
    model: str = "gemini-web",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    entry: Dict[str, Any] = {
        "time": datetime.now().isoformat(),
        "task_id": task_id,
        "execution_id": execution_id or "",
        "worker_id": worker_id or "worker_0",
        "browser_id": browser_id or "browser_0",
        "retry_count": retry_count,
        "duration": round(duration, 3),
        "model": model,
        "state": state,
        "action": action,
        "result": result if result is not None else "",
        "error": error if error is not None else "",
    }
    if extra:
        entry.update(extra)

    record = logging.LogRecord(
        name=logger.name,
        level=logging.ERROR if error else logging.INFO,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    )
    setattr(record, "structured_data", entry)
    logger.handle(record)
