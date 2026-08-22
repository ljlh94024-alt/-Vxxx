import os
from dataclasses import dataclass
from typing import Any, Dict
import yaml


@dataclass
class BrowserConfig:
    profile_path: str = "./data/profile"
    headless: bool = False
    timeout: int = 60


@dataclass
class GeminiConfig:
    url: str = "https://gemini.google.com"


@dataclass
class TaskConfig:
    timeout: int = 300


@dataclass
class RetryConfig:
    max_retry: int = 3


@dataclass
class AppConfig:
    browser: BrowserConfig
    gemini: GeminiConfig
    task: TaskConfig
    retry: RetryConfig


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load and parse application configuration with fallback defaults."""
    raw_data: Dict[str, Any] = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}

    browser_dict = raw_data.get("browser", {})
    gemini_dict = raw_data.get("gemini", {})
    task_dict = raw_data.get("task", {})
    retry_dict = raw_data.get("retry", {})

    browser_cfg = BrowserConfig(
        profile_path=str(browser_dict.get("profile_path", "./data/profile")),
        headless=bool(browser_dict.get("headless", False)),
        timeout=int(browser_dict.get("timeout", 60)),
    )

    gemini_cfg = GeminiConfig(
        url=str(gemini_dict.get("url", "https://gemini.google.com"))
    )

    task_cfg = TaskConfig(
        timeout=int(task_dict.get("timeout", 300))
    )

    retry_cfg = RetryConfig(
        max_retry=int(retry_dict.get("max_retry", 3))
    )

    return AppConfig(
        browser=browser_cfg,
        gemini=gemini_cfg,
        task=task_cfg,
        retry=retry_cfg,
    )
