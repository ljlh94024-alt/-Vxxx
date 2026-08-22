import unittest
from parser import extract_json_text, parse_response
from validator import extract_expected_keys, validate_result
from task import Task, Result


class TestParserAndValidator(unittest.TestCase):
    def test_extract_pure_json(self):
        raw = '{"answer": "hello world", "keywords": ["test", "demo"]}'
        extracted = extract_json_text(raw)
        self.assertEqual(extracted, raw)
        ok, data, err = parse_response(raw)
        self.assertTrue(ok)
        self.assertEqual(data["answer"], "hello world")

    def test_extract_markdown_json(self):
        raw = """Here is the result:
```json
{
  "answer": "ok",
  "score": 100
}
```
Hope that helps!"""
        ok, data, err = parse_response(raw)
        self.assertTrue(ok)
        self.assertEqual(data["score"], 100)

    def test_extract_embedded_json(self):
        raw = 'Some introduction prefix text {"name": "Gemini", "version": 0.1} and trailing thoughts.'
        ok, data, err = parse_response(raw)
        self.assertTrue(ok)
        self.assertEqual(data["name"], "Gemini")

    def test_validator_success(self):
        data = {"answer": "A", "keywords": ["B"]}
        expected = '{"answer": "", "keywords": []}'
        ok, err = validate_result(data, expected)
        self.assertTrue(ok)

    def test_validator_missing_keys(self):
        data = {"answer": "A"}
        expected = '{"answer": "", "keywords": []}'
        ok, err = validate_result(data, expected)
        self.assertFalse(ok)
        self.assertIn("keywords", err)

    def test_task_result_serialization(self):
        task = Task(id="t1", goal="g", prompt="p", expected_output="e")
        task_dict = task.to_dict()
        self.assertEqual(task_dict["id"], "t1")
        
        result = Result(id="t1", status="success", json_result={"status": "ok"})
        result_json = result.to_json()
        self.assertIn('"status": "success"', result_json)


if __name__ == "__main__":
    unittest.main()
