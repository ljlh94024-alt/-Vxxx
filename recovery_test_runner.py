import json
import os
import time
from typing import Any, Callable, Dict

from config import load_config
from controller import Controller
from task import Task


def load_recovery_task() -> Task:
    with open("data/test_cases/task_A_simple_json.json", "r", encoding="utf-8") as handle:
        data = json.load(handle)
    task = Task.from_dict(data)
    task.id = f"recovery_{int(time.time() * 1000)}"
    return task


def run_case(name: str, inject: Callable[[Controller], None]) -> Dict[str, Any]:
    config = load_config()
    controller = Controller(config=config)
    started_at = time.time()
    result: Dict[str, Any] = {"name": name, "passed": False}
    try:
        started, start_error = controller.browser_manager.start()
        if not started:
            raise RuntimeError(start_error)
        opened, open_error = controller.browser_manager.open_page(config.gemini.url)
        if not opened:
            raise RuntimeError(open_error)
        logged_in, login_message = controller.browser_manager.check_login()
        if not logged_in:
            raise RuntimeError(login_message)

        inject(controller)
        task_result = controller.execute_task(load_recovery_task(), keep_browser_open=True)
        result.update({
            "passed": task_result.status == "success",
            "status": task_result.status,
            "error": task_result.error,
            "extracted_json": task_result.json_result,
        })
    except Exception as exc:
        result.update({"status": "exception", "error": str(exc)})
    finally:
        result["duration_sec"] = round(time.time() - started_at, 2)
        controller.shutdown()
    return result


def close_page(controller: Controller) -> None:
    page = controller.browser_manager.get_page()
    if page is None:
        raise RuntimeError("No page available for page-close injection")
    page.close()


def close_browser_context(controller: Controller) -> None:
    context = controller.browser_manager._context
    if context is None:
        raise RuntimeError("No context available for browser-close injection")
    context.close()


def interrupt_network(controller: Controller) -> None:
    page = controller.browser_manager.get_page()
    if page is None:
        raise RuntimeError("No page available for network injection")
    page.route("**/*", lambda route: route.abort("internetdisconnected"))


def main() -> None:
    cases = [
        run_case("page_closed", close_page),
        run_case("browser_context_closed", close_browser_context),
        run_case("browser_network_interrupted", interrupt_network),
    ]
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "all_passed": all(case["passed"] for case in cases),
        "cases": cases,
    }
    output_path = "data/results/recovery_test_report.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
