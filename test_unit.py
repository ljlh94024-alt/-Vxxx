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
from benchmark_runner import get_process_metrics, summarize_metrics, subtract_traffic
from browser import BrowserManager


class TestV021RuntimeSuite(unittest.TestCase):
    def test_gemini_traffic_filter_and_delta(self):
        self.assertTrue(BrowserManager._is_gemini_traffic_host("gemini.google.com"))
        self.assertTrue(BrowserManager._is_gemini_traffic_host("alkalimakersuite-pa.clients6.google.com"))
        self.assertFalse(BrowserManager._is_gemini_traffic_host("accounts.google.com"))
        before = {
            "request_count": 2, "estimated_outbound_bytes": 100,
            "response_count": 2, "declared_inbound_bytes": 0,
            "methods": {"POST": 2},
            "by_host": {"gemini.google.com": {
                "request_count": 2, "estimated_outbound_bytes": 100,
                "response_count": 2, "declared_inbound_bytes": 0,
            }},
        }
        after = {
            "request_count": 5, "estimated_outbound_bytes": 250,
            "response_count": 4, "declared_inbound_bytes": 20,
            "methods": {"POST": 4, "GET": 1},
            "by_host": {"gemini.google.com": {
                "request_count": 5, "estimated_outbound_bytes": 250,
                "response_count": 4, "declared_inbound_bytes": 20,
            }},
        }
        delta = subtract_traffic(after, before)
        self.assertEqual(3, delta["request_count"])
        self.assertEqual(150, delta["estimated_outbound_bytes"])
        self.assertEqual({"POST": 2, "GET": 1}, delta["methods"])

    def test_process_metrics_include_python_browser_and_total(self):
        metrics = get_process_metrics()
        self.assertEqual({"python", "browser", "total"}, set(metrics))
        self.assertGreater(metrics["python"]["rss_mb"], 0)
        self.assertGreaterEqual(metrics["browser"]["process_count"], 0)
        self.assertGreaterEqual(metrics["total"]["rss_mb"], metrics["python"]["rss_mb"])

    def test_summarize_metrics(self):
        details = [
            {"metrics": {
                "python": {"rss_mb": 10.0, "cpu_percent": 2.0},
                "browser": {"rss_mb": 30.0, "cpu_percent": 4.0, "process_count": 3},
                "total": {"rss_mb": 40.0, "cpu_percent": 6.0},
            }},
            {"metrics": {
                "python": {"rss_mb": 12.0, "cpu_percent": 4.0},
                "browser": {"rss_mb": 34.0, "cpu_percent": 6.0, "process_count": 4},
                "total": {"rss_mb": 46.0, "cpu_percent": 10.0},
            }},
        ]
        summary = summarize_metrics(details)
        self.assertEqual(43.0, summary["total"]["rss_mb_avg"])
        self.assertEqual(4, summary["browser"]["process_count_max"])

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
