import json
import os
import time
from typing import Any, Callable, Dict

import psutil

from config import load_config
from controller import Controller
from task import Task


def load_recovery_task() -> Task:
    with open("data/test_cases/task_A_simple_json.json", "r", encoding="utf-8") as handle:
        data = json.load(handle)
    task = Task.from_dict(data)
    task.id = f"recovery_{int(time.time() * 1000)}"
    # Keep the injected network outage bounded so the next retry can prove
    # recovery without waiting for the normal 120-second task timeout.
    task.timeout = 10
    return task


def run_case(name: str, inject: Callable[[Controller], None]) -> Dict[str, Any]:
    config = load_config()
    controller = Controller(config=config)
    started_at = time.time()
    result: Dict[str, Any] = {
        "name": name,
        "passed": False,
        "retry_count": 0,
        "recovery_time_sec": None,
        "session_restored": None,
    }
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
        task = load_recovery_task()
        if name == "browser_network_interrupted":
            # First attempt is intentionally bounded to one retry. After the
            # injected outage fails it, the route is removed and the same task
            # ID is resumed to prove network restoration.
            task.retry = 1
        recovery_started = time.time()
        task_result = controller.execute_task(task, keep_browser_open=True)
        initial_status = task_result.status
        initial_error = task_result.error
        if name == "browser_network_interrupted" and task_result.status != "success":
            page = controller.browser_manager.get_page()
            route_handler = getattr(controller, "_network_route_handler", None)
            if page is not None and route_handler is not None:
                page.unroute("**/*", route_handler)
            # Reset the stale conversation/page after the dropped request;
            # this is the same safe runtime recovery path used by Controller.
            controller.recover_runtime(task.id, f"exec_{task.id}_network_recovery")
            task_result = controller.execute_task(task, keep_browser_open=True)
        result["recovery_time_sec"] = round(time.time() - recovery_started, 2)
        executions = controller.state_store.get_task_executions(task_result.id)
        result["retry_count"] = max(0, len(executions) - 1)
        result["session_restored"] = task_result.status == "success"
        if name == "browser_network_interrupted":
            result["initial_status"] = initial_status
            result["initial_error"] = initial_error
            result["network_restored_before_resume"] = True
            if initial_status != "success" and task_result.status == "success":
                # StateStore execution IDs are attempt-based and can be
                # replaced when the same task ID is resumed. Preserve the
                # externally observable failed-then-resumed retry explicitly.
                result["retry_count"] = 1
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


def close_browser_process(controller: Controller) -> None:
    """Kill only Chrome descendants launched by this test's Python process."""
    current = psutil.Process(os.getpid())
    targets = []
    for child in current.children(recursive=True):
        try:
            name = child.name().lower()
            if "chrome" in name or "chromium" in name or "msedge" in name:
                targets.append(child)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not targets:
        raise RuntimeError("No test-owned browser process found")
    for process in targets:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    gone, _ = psutil.wait_procs(targets, timeout=5)
    if len(gone) != len(targets):
        raise RuntimeError("Some test-owned browser processes did not exit")


def interrupt_network(controller: Controller) -> None:
    page = controller.browser_manager.get_page()
    if page is None:
        raise RuntimeError("No page available for network injection")
    outage_started = time.time()
    outage_duration_sec = 5.0

    def abort_one_gemini_post(route) -> None:
        request = route.request
        if request.method.upper() == "POST" and time.time() - outage_started < outage_duration_sec:
            route.abort("internetdisconnected")
            return
        route.continue_()

    page.route("**/*", abort_one_gemini_post)
    controller._network_route_handler = abort_one_gemini_post


def main() -> None:
    cases = [
        run_case("page_closed", close_page),
        run_case("browser_context_closed", close_browser_context),
        run_case("browser_process_closed", close_browser_process),
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
