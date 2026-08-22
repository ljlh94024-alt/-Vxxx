import unittest
import os
from unittest.mock import MagicMock, patch

from parser import extract_json_text, parse_response
from validator import extract_expected_keys, validate_result
from task import Task, Result
from store import StateStore, TaskState
from worker import load_selectors
from worker_factory import WorkerFactory
from config import load_config
from controller import Controller, State


class TestV021RuntimeSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = "data/test_state_v021.db"
        if os.path.exists(cls.test_db):
            os.remove(cls.test_db)
        cls.store = StateStore(db_path=cls.test_db)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except Exception:
                pass

    def test_parser_and_validation(self):
        raw = """```json
        {
          "features": ["speed", "safety"],
          "version": 0.21
        }
        ```"""
        ok, data, err = parse_response(raw)
        self.assertTrue(ok)
        self.assertEqual(data["version"], 0.21)

        v_ok, v_err = validate_result(data, '{"features": [], "version": 0}')
        self.assertTrue(v_ok)

    def test_state_store_lifecycle_and_executions(self):
        task_id = "test_task_history_001"
        self.store.create_task(task_id)
        
        # Execution 1: Failed
        self.store.record_execution("exec_1", task_id, attempt=1, state=TaskState.FAILED, error="Timeout", duration=1.2)
        
        # Execution 2: Success
        self.store.record_execution("exec_2", task_id, attempt=2, state=TaskState.SUCCESS, duration=0.8)
        self.store.update_state(task_id, TaskState.SUCCESS, result={"answer": "ok"})

        task_record = self.store.get_task(task_id)
        self.assertEqual(task_record["state"], TaskState.SUCCESS)

        execs = self.store.get_task_executions(task_id)
        self.assertEqual(len(execs), 2)
        self.assertEqual(execs[0]["state"], TaskState.FAILED)
        self.assertEqual(execs[1]["state"], TaskState.SUCCESS)

    def test_worker_factory(self):
        mock_page = MagicMock()
        worker = WorkerFactory.create_worker("gemini", mock_page)
        self.assertEqual(worker.model_name, "gemini-web")

    def test_controller_success_flow_mock(self):
        config = load_config()
        controller = Controller(config=config, db_path=self.test_db)

        # Mock BrowserManager methods
        controller.browser_manager.health_check = MagicMock(return_value=(True, "ok"))
        controller.browser_manager.start = MagicMock(return_value=(True, ""))
        controller.browser_manager.open_page = MagicMock(return_value=(True, ""))
        controller.browser_manager.check_login = MagicMock(return_value=(True, "authenticated"))
        mock_page = MagicMock()
        mock_page.is_closed = MagicMock(return_value=False)
        controller.browser_manager.get_page = MagicMock(return_value=mock_page)

        # Mock Worker
        mock_worker = MagicMock()
        mock_worker.send_prompt = MagicMock(return_value=(True, ""))
        mock_worker.wait_response = MagicMock(return_value=(True, ""))
        mock_worker.get_response = MagicMock(return_value=(True, '{"status": "completed"}', ""))

        with patch.object(WorkerFactory, "create_worker", return_value=mock_worker):
            task = Task(id="task_mock_001", goal="test", prompt="test", expected_output='{"status": ""}')
            result = controller.execute_task(task, keep_browser_open=True)
            self.assertEqual(result.status, "success")
            self.assertEqual(result.json_result.get("status"), "completed")

    def test_controller_retry_then_success_mock(self):
        config = load_config()
        controller = Controller(config=config, db_path=self.test_db)

        controller.browser_manager.health_check = MagicMock(return_value=(True, "ok"))
        controller.browser_manager.open_page = MagicMock(return_value=(True, ""))
        controller.browser_manager.check_login = MagicMock(return_value=(True, "authenticated"))
        mock_page = MagicMock()
        mock_page.is_closed = MagicMock(return_value=False)
        controller.browser_manager.get_page = MagicMock(return_value=mock_page)

        mock_worker = MagicMock()
        # Attempt 1: parse failure (invalid JSON), Attempt 2: valid JSON
        mock_worker.send_prompt = MagicMock(return_value=(True, ""))
        mock_worker.wait_response = MagicMock(return_value=(True, ""))
        mock_worker.get_response = MagicMock(side_effect=[
            (True, "Invalid non-json response", ""),
            (True, '{"status": "fixed_on_retry"}', ""),
        ])

        with patch.object(WorkerFactory, "create_worker", return_value=mock_worker):
            task = Task(id="task_mock_retry", goal="test", prompt="test", expected_output='{"status": ""}')
            result = controller.execute_task(task, keep_browser_open=True)
            self.assertEqual(result.status, "success")
            self.assertEqual(result.json_result.get("status"), "fixed_on_retry")


if __name__ == "__main__":
    unittest.main()
