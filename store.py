import os
import sqlite3
import json
from datetime import datetime
from typing import Any, Dict, List, Optional


class TaskState:
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class StateStore:
    """
    SQLite-backed state storage for managing task records and execution histories.
    """

    def __init__(self, db_path: str = "data/state.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS task_records (
                    task_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_time TEXT NOT NULL,
                    updated_time TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    execution_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    error TEXT,
                    duration REAL,
                    created_time TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES task_records(task_id)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def create_task(self, task_id: str) -> None:
        now = datetime.now().isoformat()
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO task_records (task_id, state, result, error, created_time, updated_time)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    state = excluded.state,
                    updated_time = excluded.updated_time
                """,
                (task_id, TaskState.CREATED, "", "", now, now),
            )
            conn.commit()
        finally:
            conn.close()

    def update_state(
        self,
        task_id: str,
        state: str,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> None:
        now = datetime.now().isoformat()
        result_str = None
        if result is not None:
            if isinstance(result, (dict, list)):
                result_str = json.dumps(result, ensure_ascii=False)
            else:
                result_str = str(result)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if result_str is not None and error is not None:
                cursor.execute(
                    """
                    UPDATE task_records
                    SET state = ?, result = ?, error = ?, updated_time = ?
                    WHERE task_id = ?
                    """,
                    (state, result_str, error, now, task_id),
                )
            elif result_str is not None:
                cursor.execute(
                    """
                    UPDATE task_records
                    SET state = ?, result = ?, updated_time = ?
                    WHERE task_id = ?
                    """,
                    (state, result_str, now, task_id),
                )
            elif error is not None:
                cursor.execute(
                    """
                    UPDATE task_records
                    SET state = ?, error = ?, updated_time = ?
                    WHERE task_id = ?
                    """,
                    (state, error, now, task_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE task_records
                    SET state = ?, updated_time = ?
                    WHERE task_id = ?
                    """,
                    (state, now, task_id),
                )
            conn.commit()
        finally:
            conn.close()

    def record_execution(
        self,
        execution_id: str,
        task_id: str,
        attempt: int,
        state: str,
        error: str = "",
        duration: float = 0.0,
    ) -> None:
        now = datetime.now().isoformat()
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO executions (execution_id, task_id, attempt, state, error, duration, created_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET
                    state = excluded.state,
                    error = excluded.error,
                    duration = excluded.duration
                """,
                (execution_id, task_id, attempt, state, error, round(duration, 3), now),
            )
            conn.commit()
        finally:
            conn.close()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT task_id, state, result, error, created_time, updated_time FROM task_records WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            result_raw = row["result"]
            parsed_result = result_raw
            if result_raw:
                try:
                    parsed_result = json.loads(result_raw)
                except Exception:
                    pass

            return {
                "task_id": row["task_id"],
                "state": row["state"],
                "result": parsed_result,
                "error": row["error"],
                "created_time": row["created_time"],
                "updated_time": row["updated_time"],
            }
        finally:
            conn.close()

    def get_task_executions(self, task_id: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT execution_id, task_id, attempt, state, error, duration, created_time FROM executions WHERE task_id = ? ORDER BY attempt ASC",
                (task_id,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT task_id, state, result, error, created_time, updated_time FROM task_records ORDER BY created_time DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
