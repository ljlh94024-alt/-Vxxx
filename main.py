import sys
import os
import json
import argparse
from datetime import datetime

from config import load_config
from task import Task, Result
from controller import Controller


def save_result_to_file(result: Result, output_dir: str = "./data/results") -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{result.id}.json"
    file_path = os.path.join(output_dir, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(result.to_json())
    return file_path


def main():
    parser = argparse.ArgumentParser(description="Gemini Browser Client v0.1 CLI")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--task-file", help="Path to JSON task definition file")
    parser.add_argument("--task-id", default="task_cli_001", help="Task ID for direct CLI execution")
    parser.add_argument("--goal", default="测试问答任务", help="Task goal")
    parser.add_argument("--prompt", default="请列出人工智能的三大核心要素，并给出简短解释。", help="Prompt to execute")
    parser.add_argument("--expected-output", default='{"elements": [], "summary": ""}', help="Expected JSON structure or required fields")
    parser.add_argument("--headless", action="store_true", help="Override config and run in headless mode")

    args = parser.parse_args()

    config = load_config(args.config)
    if args.headless:
        config.browser.headless = True

    if args.task_file and os.path.exists(args.task_file):
        with open(args.task_file, "r", encoding="utf-8") as f:
            task_dict = json.load(f)
        task = Task.from_dict(task_dict)
    else:
        task = Task(
            id=args.task_id,
            goal=args.goal,
            prompt=args.prompt,
            expected_output=args.expected_output,
            timeout=config.task.timeout,
            retry=config.retry.max_retry,
        )

    print("=" * 60)
    print(f"Starting Gemini Browser Client Task: {task.id}")
    print(f"Goal: {task.goal}")
    print("=" * 60)

    controller = Controller(config)
    result = controller.execute_task(task)

    saved_path = save_result_to_file(result)

    print("\n" + "=" * 60)
    print(f"Task Execution Finished with Status: {result.status.upper()}")
    print(f"Result saved to: {saved_path}")
    print("Result Payload:")
    print(result.to_json())
    print("=" * 60)

    if result.status != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
