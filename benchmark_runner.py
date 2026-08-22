import os
import sys
import time
import json
import argparse
from typing import List, Dict, Any, Iterable

from config import load_config
from task import Task, Result
from controller import Controller
from store import StateStore
from parser import parse_response


def _sum_rss_mb(processes: Iterable[Any]) -> float:
    total_bytes = 0
    for process in processes:
        try:
            total_bytes += process.memory_info().rss
        except Exception:
            continue
    return round(total_bytes / 1024 / 1024, 2)


def _sample_cpu_percent(processes: Iterable[Any], interval: float = 0.2) -> float:
    live_processes = []
    for process in processes:
        try:
            process.cpu_percent(interval=None)
            live_processes.append(process)
        except Exception:
            continue
    if live_processes:
        time.sleep(interval)
    total = 0.0
    for process in live_processes:
        try:
            total += process.cpu_percent(interval=None)
        except Exception:
            continue
    return round(total, 2)


def get_process_metrics() -> Dict[str, Any]:
    """Collect CPU and RSS for this Python process and its browser children."""
    import psutil

    python_process = psutil.Process(os.getpid())
    browser_names = ("chrome", "chromium", "msedge")
    browser_processes = []
    for child in python_process.children(recursive=True):
        try:
            if any(name in child.name().lower() for name in browser_names):
                browser_processes.append(child)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    python_cpu = _sample_cpu_percent([python_process])
    browser_cpu = _sample_cpu_percent(browser_processes)
    python_rss = _sum_rss_mb([python_process])
    browser_rss = _sum_rss_mb(browser_processes)
    return {
        "python": {"pid": python_process.pid, "rss_mb": python_rss, "cpu_percent": python_cpu},
        "browser": {
            "process_count": len(browser_processes),
            "rss_mb": browser_rss,
            "cpu_percent": browser_cpu,
        },
        "total": {
            "rss_mb": round(python_rss + browser_rss, 2),
            "cpu_percent": round(python_cpu + browser_cpu, 2),
        },
    }


def summarize_metrics(round_details: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for group in ("python", "browser", "total"):
        rss_values = [detail["metrics"][group]["rss_mb"] for detail in round_details]
        cpu_values = [detail["metrics"][group]["cpu_percent"] for detail in round_details]
        summary[group] = {
            "rss_mb_avg": round(sum(rss_values) / len(rss_values), 2) if rss_values else 0.0,
            "rss_mb_min": min(rss_values, default=0.0),
            "rss_mb_max": max(rss_values, default=0.0),
            "cpu_percent_avg": round(sum(cpu_values) / len(cpu_values), 2) if cpu_values else 0.0,
            "cpu_percent_max": max(cpu_values, default=0.0),
        }
    browser_counts = [detail["metrics"]["browser"]["process_count"] for detail in round_details]
    summary["browser"]["process_count_max"] = max(browser_counts, default=0)
    return summary


def subtract_traffic(after: Dict[str, Any], before: Dict[str, Any]) -> Dict[str, Any]:
    """Create a non-negative per-round delta from cumulative traffic counters."""
    result = {}
    for key in ("request_count", "estimated_outbound_bytes", "response_count", "declared_inbound_bytes"):
        result[key] = max(0, after.get(key, 0) - before.get(key, 0))
    result["methods"] = {
        key: max(0, value - before.get("methods", {}).get(key, 0))
        for key, value in after.get("methods", {}).items()
        if value - before.get("methods", {}).get(key, 0) > 0
    }
    result["by_host"] = {}
    for host, values in after.get("by_host", {}).items():
        old = before.get("by_host", {}).get(host, {})
        delta = {key: max(0, values.get(key, 0) - old.get(key, 0)) for key in values}
        if any(delta.values()):
            result["by_host"][host] = delta
    return result


def summarize_traffic(round_details: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = {"request_count": 0, "estimated_outbound_bytes": 0,
             "response_count": 0, "declared_inbound_bytes": 0, "methods": {}, "by_host": {}}
    for detail in round_details:
        traffic = detail["gemini_traffic"]
        for key in ("request_count", "estimated_outbound_bytes", "response_count", "declared_inbound_bytes"):
            total[key] += traffic[key]
        for method, count in traffic["methods"].items():
            total["methods"][method] = total["methods"].get(method, 0) + count
        for host, values in traffic["by_host"].items():
            target = total["by_host"].setdefault(host, {key: 0 for key in values})
            for key, value in values.items():
                target[key] += value
    total["measurement_note"] = (
        "Outbound is an application-layer estimate from method, URL, headers and body; "
        "it excludes TLS and HTTP/2 framing. Inbound counts only declared Content-Length. "
        "No URL query, header value, cookie, or request body is stored."
    )
    return total


def load_task_file(file_path: str) -> Task:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Task.from_dict(data)


def run_benchmark(
    rounds: int = 10,
    headless: bool = False,
    task_files: List[str] = None,
    output_report: str = "data/results/benchmark_report.json",
):
    print("=" * 70)
    print(f"Gemini Browser Client v0.2.1-V1.1 Stability Benchmark Runner")
    print(f"Total Rounds: {rounds} | Headless: {headless}")
    print("=" * 70)

    config = load_config()
    config.browser.headless = headless

    controller = Controller(config=config)
    store = StateStore()

    if not task_files:
        task_files = [
            "data/test_cases/task_A_simple_json.json",
            "data/test_cases/task_B_long_text.json",
            "data/test_cases/task_C_complex_format.json",
        ]

    tasks_pool: List[Task] = []
    for tf in task_files:
        if os.path.exists(tf):
            tasks_pool.append(load_task_file(tf))

    if not tasks_pool:
        print("Error: No test task files found.")
        return

    success_count = 0
    failed_count = 0
    retry_count = 0
    extraction_verified_count = 0
    durations: List[float] = []
    round_details: List[Dict[str, Any]] = []
    run_id = time.strftime("%Y%m%d_%H%M%S")

    start_total_time = time.time()

    try:
        for i in range(1, rounds + 1):
            base_task = tasks_pool[(i - 1) % len(tasks_pool)]
            task = Task(
                id=f"{base_task.id}_{run_id}_r{i}",
                goal=base_task.goal,
                prompt=base_task.prompt,
                expected_output=base_task.expected_output,
                timeout=base_task.timeout,
                retry=base_task.retry,
            )

            print(f"[{i}/{rounds}] Running task: {task.id} ... ", end="", flush=True)
            traffic_before = controller.browser_manager.get_gemini_traffic_snapshot()
            r_start = time.time()
            res = controller.execute_task(task, keep_browser_open=True)
            r_dur = round(time.time() - r_start, 2)
            durations.append(r_dur)

            metrics = get_process_metrics()
            traffic_after = controller.browser_manager.get_gemini_traffic_snapshot()
            gemini_traffic = subtract_traffic(traffic_after, traffic_before)
            executions = store.get_task_executions(task.id)
            round_retry_count = max(0, len(executions) - 1)
            retry_count += round_retry_count
            extraction_ok = False
            extraction_error = ""
            if res.content:
                parsed_ok, parsed_again, parsed_error = parse_response(res.content)
                extraction_ok = parsed_ok and parsed_again == res.json_result
                if not extraction_ok:
                    extraction_error = parsed_error or "Re-parsed page response differs from Result.json_result"
            if extraction_ok:
                extraction_verified_count += 1

            if res.status == "success":
                success_count += 1
                print(f"SUCCESS ({r_dur}s) | Mem: {metrics['total']['rss_mb']}MB | Retry: {round_retry_count}")
            else:
                failed_count += 1
                print(f"FAILED ({r_dur}s) | Error: {res.error[:40]}... | Mem: {metrics['total']['rss_mb']}MB | Retry: {round_retry_count}")

            round_details.append({
                "round": i,
                "task_id": task.id,
                "status": res.status,
                "duration": r_dur,
                "error": res.error,
                "retry_count": round_retry_count,
                "response_raw": res.content,
                "parsed_result": res.json_result,
                "extraction_verified": extraction_ok,
                "extraction_error": extraction_error,
                "metrics": metrics,
                "gemini_traffic": gemini_traffic,
            })

            time.sleep(1.0)

    finally:
        controller.shutdown()

    total_duration = round(time.time() - start_total_time, 2)
    avg_duration = round(sum(durations) / len(durations), 2) if durations else 0.0
    success_rate = round((success_count / rounds) * 100, 2) if rounds > 0 else 0.0

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "run_id": run_id,
        "mode": "headless" if headless else "gui",
        "total_rounds": rounds,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate_percent": success_rate,
        "total_duration_sec": total_duration,
        "avg_duration_sec": avg_duration,
        "retry_count": retry_count,
        "extraction_verified_count": extraction_verified_count,
        "extraction_verified_rate_percent": round(
            (extraction_verified_count / rounds) * 100, 2
        ) if rounds > 0 else 0.0,
        "resource_summary": summarize_metrics(round_details),
        "gemini_traffic_summary": summarize_traffic(round_details),
        "round_details": round_details,
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_report)), exist_ok=True)
    with open(output_report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY REPORT")
    print("=" * 70)
    print(f"Success Rate: {success_rate}% ({success_count}/{rounds})")
    print(f"Total Time:   {total_duration}s (Avg: {avg_duration}s/task)")
    print(f"Report saved: {output_report}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Gemini Browser Client v0.2.1-V1.1 Benchmark Runner")
    parser.add_argument("--rounds", type=int, default=10, help="Number of test rounds to execute (default: 10)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--output", default="data/results/benchmark_report.json", help="Output report file path")
    args = parser.parse_args()

    run_benchmark(rounds=args.rounds, headless=args.headless, output_report=args.output)


if __name__ == "__main__":
    main()
