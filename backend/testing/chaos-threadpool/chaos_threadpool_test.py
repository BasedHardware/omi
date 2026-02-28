#!/usr/bin/env python3
import argparse
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Optional

TASK_NAMES = [
    "save_structured_vector",
    "_extract_memories",
    "_extract_trends",
    "_save_action_items",
    "_update_goal_progress",
    "conversation_created_webhook",
    "update_personas_async",
]


@dataclass
class MonitorResult:
    peak_total_threads: int = 0
    peak_bg_threads: int = 0
    peak_pool_threads: int = 0


class ThreadMonitor:
    def __init__(self, sample_interval: float) -> None:
        self.sample_interval = sample_interval
        self.stop_event = threading.Event()
        self.result = MonitorResult()
        self._thread = threading.Thread(target=self._run, name="monitor", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self._thread.join()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            threads = threading.enumerate()
            total = len(threads)
            bg = 0
            pool = 0
            for t in threads:
                name = t.name
                if name.startswith("bg-"):
                    bg += 1
                if name.startswith("ThreadPoolExecutor") or name.startswith("pool"):
                    pool += 1
            if total > self.result.peak_total_threads:
                self.result.peak_total_threads = total
            if bg > self.result.peak_bg_threads:
                self.result.peak_bg_threads = bg
            if pool > self.result.peak_pool_threads:
                self.result.peak_pool_threads = pool
            time.sleep(self.sample_interval)


def slow_task(task_name: str, sleep_min: float, sleep_max: float) -> None:
    _ = task_name
    time.sleep(random.uniform(sleep_min, sleep_max))


def process_conversation_vulnerable(
    conv_id: int,
    sleep_min: float,
    sleep_max: float,
    threads: List[threading.Thread],
) -> None:
    for task_name in TASK_NAMES:
        t = threading.Thread(
            target=slow_task,
            args=(task_name, sleep_min, sleep_max),
            name=f"bg-{task_name}-{conv_id}",
        )
        t.start()
        threads.append(t)


def process_conversation_fixed(
    conv_id: int,
    sleep_min: float,
    sleep_max: float,
    executor: ThreadPoolExecutor,
) -> None:
    for task_name in TASK_NAMES:
        executor.submit(slow_task, task_name, sleep_min, sleep_max)
    _ = conv_id


def run_variant(
    mode: str,
    conversations: int,
    sleep_min: float,
    sleep_max: float,
    max_workers: int,
    sample_interval: float,
    launch_interval: float,
) -> dict:
    if mode not in {"vulnerable", "fixed"}:
        raise ValueError(f"Unknown mode: {mode}")

    monitor = ThreadMonitor(sample_interval=sample_interval)
    monitor.start()

    start_time = time.time()
    threads: List[threading.Thread] = []
    executor: Optional[ThreadPoolExecutor] = None

    if mode == "fixed":
        executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pool")

    for conv_id in range(conversations):
        if mode == "vulnerable":
            process_conversation_vulnerable(conv_id, sleep_min, sleep_max, threads)
        else:
            assert executor is not None
            process_conversation_fixed(conv_id, sleep_min, sleep_max, executor)

        if launch_interval > 0:
            time.sleep(launch_interval)

    if mode == "vulnerable":
        for t in threads:
            t.join()
    else:
        assert executor is not None
        executor.shutdown(wait=True)

    elapsed = time.time() - start_time
    monitor.stop()

    result = {
        "mode": mode,
        "conversations": conversations,
        "tasks_per_conversation": len(TASK_NAMES),
        "total_tasks": conversations * len(TASK_NAMES),
        "sleep_min_s": sleep_min,
        "sleep_max_s": sleep_max,
        "launch_interval_s": launch_interval,
        "max_workers": max_workers,
        "elapsed_s": round(elapsed, 2),
        "peak_total_threads": monitor.result.peak_total_threads,
        "peak_bg_threads": monitor.result.peak_bg_threads,
        "peak_pool_threads": monitor.result.peak_pool_threads,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Chaos test for thread explosion in process_conversation")
    parser.add_argument("--mode", choices=["vulnerable", "fixed"], required=True)
    parser.add_argument("--conversations", type=int, default=50)
    parser.add_argument("--sleep-min", type=float, default=2.0)
    parser.add_argument("--sleep-max", type=float, default=5.0)
    parser.add_argument("--max-workers", type=int, default=32)
    parser.add_argument("--sample-interval", type=float, default=0.05)
    parser.add_argument("--launch-interval", type=float, default=0.005)
    parser.add_argument("--seed", type=int, default=4827)
    args = parser.parse_args()

    random.seed(args.seed)

    result = run_variant(
        mode=args.mode,
        conversations=args.conversations,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
        max_workers=args.max_workers,
        sample_interval=args.sample_interval,
        launch_interval=args.launch_interval,
    )

    print("RESULT: " + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
