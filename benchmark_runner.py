import os
import sys
import time
import json
import argparse
from typing import List, Dict, Any

from config import load_config
from task import Task, Result
from controller import Controller
from store import StateStore


def get_process_metrics():
    """Lightweight resource monitoring for Python process."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        return {
            "rss_mb": round(mem_info.rss / 1024 / 1024, 2),
            "cpu_percent": process.cpu_percent(interval=0.1),
        }
    except Exception:
        return {"rss_mb": 0.0, "cpu_percent": 0.0}


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
    durations: List[float] = []
    round_details: List[Dict[str, Any]] = []

    start_total_time = time.time()

    try:
        for i in range(1, rounds + 1):
            base_task = tasks_pool[(i - 1) % len(tasks_pool)]
            task = Task(
                id=f"{base_task.id}_r{i}",
                goal=base_task.goal,
                prompt=base_task.prompt,
                expected_output=base_task.expected_output,
                timeout=base_task.timeout,
                retry=base_task.retry,
            )

            print(f"[{i}/{rounds}] Running task: {task.id} ... ", end="", flush=True)
            r_start = time.time()
            res = controller.execute_task(task, keep_browser_open=True)
            r_dur = round(time.time() - r_start, 2)
            durations.append(r_dur)

            metrics = get_process_metrics()

            if res.status == "success":
                success_count += 1
                print(f"SUCCESS ({r_dur}s) | Mem: {metrics['rss_mb']}MB")
            else:
                failed_count += 1
                print(f"FAILED ({r_dur}s) | Error: {res.error[:40]}... | Mem: {metrics['rss_mb']}MB")

            round_details.append({
                "round": i,
                "task_id": task.id,
                "status": res.status,
                "duration": r_dur,
                "error": res.error,
                "metrics": metrics,
            })

            time.sleep(1.0)

    finally:
        controller.shutdown()

    total_duration = round(time.time() - start_total_time, 2)
    avg_duration = round(sum(durations) / len(durations), 2) if durations else 0.0
    success_rate = round((success_count / rounds) * 100, 2) if rounds > 0 else 0.0

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": "headless" if headless else "gui",
        "total_rounds": rounds,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate_percent": success_rate,
        "total_duration_sec": total_duration,
        "avg_duration_sec": avg_duration,
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
