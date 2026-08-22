import unittest
import os
from parser import extract_json_text, parse_response
from validator import extract_expected_keys, validate_result
from task import Task, Result
from store import StateStore, TaskState
from worker import load_selectors


class TestV02RuntimeSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = "data/test_state.db"
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
          "version": 0.2
        }
        ```"""
        ok, data, err = parse_response(raw)
        self.assertTrue(ok)
        self.assertEqual(data["version"], 0.2)

        v_ok, v_err = validate_result(data, '{"features": [], "version": 0}')
        self.assertTrue(v_ok)

    def test_state_store_lifecycle(self):
        task_id = "test_task_001"
        self.store.create_task(task_id)
        record = self.store.get_task(task_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["state"], TaskState.CREATED)

        self.store.update_state(task_id, TaskState.RUNNING)
        record = self.store.get_task(task_id)
        self.assertEqual(record["state"], TaskState.RUNNING)

        self.store.update_state(task_id, TaskState.SUCCESS, result={"status": "all_good"})
        record = self.store.get_task(task_id)
        self.assertEqual(record["state"], TaskState.SUCCESS)
        self.assertEqual(record["result"]["status"], "all_good")

    def test_selector_loader(self):
        selectors = load_selectors("selectors/gemini.yaml")
        self.assertIn("prompt_input", selectors)
        self.assertIn("aria", selectors["prompt_input"])
        self.assertIn("send_button", selectors)


if __name__ == "__main__":
    unittest.main()
