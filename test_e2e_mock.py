import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from config import load_config
from task import Task, Result
from controller import Controller, State
from store import StateStore, TaskState
from worker_factory import WorkerFactory
from benchmark_runner import run_benchmark


class TestE2EAutomatedValidation(unittest.TestCase):
    """
    Simulates end-to-end multi-task execution, recovery, and benchmark cycles
    under mock web interface conditions.
    """

    def setUp(self):
        self.test_db = "data/e2e_test_state.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.store = StateStore(db_path=self.test_db)

    def tearDown(self):
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass

    def test_e2e_task_suite_mock(self):
        config = load_config()
        controller = Controller(config=config, db_path=self.test_db)

        # Mock browser readiness & authentication
        controller.browser_manager.health_check = MagicMock(return_value=(True, "healthy"))
        controller.browser_manager.start = MagicMock(return_value=(True, ""))
        controller.browser_manager.open_page = MagicMock(return_value=(True, ""))
        controller.browser_manager.check_login = MagicMock(return_value=(True, "authenticated"))
        mock_page = MagicMock()
        mock_page.is_closed = MagicMock(return_value=False)
        controller.browser_manager.get_page = MagicMock(return_value=mock_page)

        # Mock worker returning valid structured responses for each task type
        mock_worker = MagicMock()
        mock_worker.send_prompt = MagicMock(return_value=(True, ""))
        mock_worker.wait_response = MagicMock(return_value=(True, ""))

        # Task A response
        mock_worker.get_response = MagicMock(return_value=(
            True,
            '{"languages": ["Python", "JavaScript", "Go"], "summary": "Top 3 languages in 2026"}',
            ""
        ))

        with patch.object(WorkerFactory, "create_worker", return_value=mock_worker):
            task_a = Task(
                id="task_A_val",
                goal="获取基础结构",
                prompt="3种语言",
                expected_output='{"languages": [], "summary": ""}',
            )
            res_a = controller.execute_task(task_a, keep_browser_open=True)
            self.assertEqual(res_a.status, "success")
            self.assertEqual(len(res_a.json_result["languages"]), 3)

            # Verify SQLite task and execution records
            rec_a = controller.state_store.get_task("task_A_val")
            self.assertEqual(rec_a["state"], TaskState.SUCCESS)
            execs_a = controller.state_store.get_task_executions("task_A_val")
            self.assertEqual(len(execs_a), 1)
            self.assertEqual(execs_a[0]["state"], TaskState.SUCCESS)

    def test_e2e_recovery_on_browser_crash(self):
        config = load_config()
        controller = Controller(config=config, db_path=self.test_db)

        controller.browser_manager.health_check = MagicMock(return_value=(True, "healthy"))
        controller.browser_manager.start = MagicMock(return_value=(True, ""))
        controller.browser_manager.open_page = MagicMock(return_value=(True, ""))
        controller.browser_manager.check_login = MagicMock(return_value=(True, "authenticated"))
        mock_page = MagicMock()
        mock_page.is_closed = MagicMock(return_value=False)
        controller.browser_manager.get_page = MagicMock(return_value=mock_page)

        # Trigger crash on first attempt, recovery, then success on 2nd attempt
        mock_worker_crashed = MagicMock()
        mock_worker_crashed.send_prompt = MagicMock(return_value=(False, "Target page, context or browser has been closed"))

        mock_worker_recovered = MagicMock()
        mock_worker_recovered.send_prompt = MagicMock(return_value=(True, ""))
        mock_worker_recovered.wait_response = MagicMock(return_value=(True, ""))
        mock_worker_recovered.get_response = MagicMock(return_value=(True, '{"status": "recovered_successfully"}', ""))

        controller.recover_runtime = MagicMock(return_value=True)

        with patch.object(WorkerFactory, "create_worker", side_effect=[mock_worker_crashed, mock_worker_recovered]):
            task = Task(id="task_crash_rec", goal="test recovery", prompt="test", expected_output='{"status": ""}')
            result = controller.execute_task(task, keep_browser_open=True)
            self.assertEqual(result.status, "success")
            self.assertEqual(result.json_result["status"], "recovered_successfully")


if __name__ == "__main__":
    unittest.main()
