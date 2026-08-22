import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class Task:
    id: str
    goal: str
    prompt: str
    expected_output: str = ""
    timeout: int = 300
    retry: int = 3

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            id=str(data.get("id", "")),
            goal=str(data.get("goal", "")),
            prompt=str(data.get("prompt", "")),
            expected_output=str(data.get("expected_output", "")),
            timeout=int(data.get("timeout", 300)),
            retry=int(data.get("retry", 3)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Result:
    id: str
    status: str
    content: str = ""
    json_result: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    screenshot: str = ""
    time: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Result":
        return cls(
            id=str(data.get("id", "")),
            status=str(data.get("status", "")),
            content=str(data.get("content", "")),
            json_result=data.get("json_result", {}),
            error=str(data.get("error", "")),
            screenshot=str(data.get("screenshot", "")),
            time=str(data.get("time", datetime.now().isoformat())),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
