#!/usr/bin/env python3
"""Make the difference between concurrency and parallelism visible.

Concurrency: several tasks are in progress, but one worker switches between
them when they pause. Parallelism: several workers execute CPU work at the
same time. This script needs only the Python standard library.
"""

from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from time import perf_counter, sleep


TASK_COUNT = 3
WAIT_SECONDS = 1.0
PRIME_LIMIT = 350_000


@dataclass(frozen=True)
class WaitResult:
    task_id: int
    pid: int
    thread_name: str
    started: float
    finished: float


async def concurrent_waiting_task(task_id: int, clock_origin: float) -> WaitResult:
    started = perf_counter() - clock_origin
    pid = os.getpid()
    thread_name = threading.current_thread().name
    await asyncio.sleep(WAIT_SECONDS)
    finished = perf_counter() - clock_origin
    return WaitResult(task_id, pid, thread_name, started, finished)


def print_section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def print_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    widths = [
        max(len(headers[column]), *(len(row[column]) for row in rows))
        for column in range(len(headers))
    ]

    def formatted(row: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(width) for value, width in zip(row, widths))

    print(f"  {formatted(headers)}")
    print(f"  {formatted(tuple('-' * width for width in widths))}")
    for row in rows:
        print(f"  {formatted(row)}")


def show_concurrency() -> None:
    print_section("Experiment A: I/O-bound tasks (sleep)")
    print("Question: can async code overlap time that sync code spends waiting?")

    sequential_started = perf_counter()
    for _ in range(TASK_COUNT):
        sleep(WAIT_SECONDS)
    sequential_elapsed = perf_counter() - sequential_started

    started_at = perf_counter()

    async def run_tasks() -> list[WaitResult]:
        return await asyncio.gather(
            *(concurrent_waiting_task(task_id, started_at) for task_id in range(1, TASK_COUNT + 1))
        )

    results = asyncio.run(run_tasks())
    concurrent_elapsed = perf_counter() - started_at

    print("\nTask layout:")
    print("  SYNC / sequential    [task 1 WAIT] -> [task 2 WAIT] -> [task 3 WAIT]")
    print("  ASYNC / concurrent   [task 1 WAIT]")
    print("                       [task 2 WAIT]   <- same time window")
    print("                       [task 3 WAIT]")

    print("\nMeasurements:")
    print_table(
        ("Mode", "Operation", "Workers", "Elapsed"),
        [
            (
                "SYNC / sequential",
                "time.sleep()",
                "1 process / 1 thread",
                f"{sequential_elapsed:.2f}s",
            ),
            (
                "ASYNC / concurrent",
                "await asyncio.sleep()",
                "1 process / 1 thread",
                f"{concurrent_elapsed:.2f}s",
            ),
        ],
    )

    speedup = sequential_elapsed / concurrent_elapsed
    print("\nEvidence:")
    print(f"  All tasks used pid={results[0].pid}, thread={results[0].thread_name}.")
    print(f"  Their waits overlapped, making the run {speedup:.1f}x faster.")
    print("  The CPU did not execute the tasks in parallel.")
    print("  await asyncio.sleep() yielded control so the event loop could start another task.")


@dataclass(frozen=True)
class CpuResult:
    task_id: int
    pid: int
    started: float
    finished: float
    primes_found: int


def count_primes(task_id: int, limit: int, clock_origin: float) -> CpuResult:
    """Do deliberately CPU-heavy work and record where and when it ran."""
    started = perf_counter() - clock_origin
    primes_found = 0

    for candidate in range(2, limit):
        is_prime = True
        factor = 2
        while factor * factor <= candidate:
            if candidate % factor == 0:
                is_prime = False
                break
            factor += 1
        if is_prime:
            primes_found += 1

    finished = perf_counter() - clock_origin
    return CpuResult(task_id, os.getpid(), started, finished, primes_found)


def show_parallelism() -> None:
    available_cpus = os.cpu_count() or 1
    worker_count = min(TASK_COUNT, available_cpus)
    print_section("Experiment B: CPU-bound tasks (count primes)")
    print("Question: can multiple CPU cores perform calculations at the same time?")

    started_at = perf_counter()
    sequential_results = [
        count_primes(task_id, PRIME_LIMIT, started_at)
        for task_id in range(1, TASK_COUNT + 1)
    ]
    sequential_elapsed = perf_counter() - started_at

    started_at = perf_counter()
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        parallel_results = list(
            executor.map(
                count_primes,
                range(1, TASK_COUNT + 1),
                [PRIME_LIMIT] * TASK_COUNT,
                [started_at] * TASK_COUNT,
            )
        )
    parallel_elapsed = perf_counter() - started_at

    print("\nTask layout:")
    print("  SYNC / sequential:")
    print("    one worker  [task 1 WORK] -> [task 2 WORK] -> [task 3 WORK]")
    print("  PARALLEL:")
    for result in parallel_results:
        print(f"    pid {result.pid}  [task {result.task_id} WORK]")

    print("\nMeasurements:")
    print_table(
        ("Mode", "Workers", "CPU activity", "Elapsed"),
        [
            (
                "SYNC / sequential",
                "1 process",
                "1 core busy",
                f"{sequential_elapsed:.2f}s",
            ),
            (
                "PARALLEL",
                f"{worker_count} processes",
                f"up to {worker_count} cores busy",
                f"{parallel_elapsed:.2f}s",
            ),
        ],
    )

    print("\nParallel worker intervals:")
    print_table(
        ("Task", "PID", "Started", "Finished"),
        [
            (
                str(result.task_id),
                str(result.pid),
                f"+{result.started:.2f}s",
                f"+{result.finished:.2f}s",
            )
            for result in parallel_results
        ],
    )

    if worker_count == 1:
        print("\nThis machine exposes one CPU, so true parallel execution is unavailable.")
    else:
        speedup = sequential_elapsed / parallel_elapsed
        sequential_pid = sequential_results[0].pid
        print("\nEvidence:")
        print(f"  Sequential work used one pid ({sequential_pid}).")
        print("  Parallel work used different PIDs with overlapping time intervals.")
        print(f"  Separate processes used multiple cores and ran {speedup:.1f}x faster.")


def main() -> None:
    print("\nConcurrency vs. parallelism")
    print("===========================")
    print("Two paired experiments: waiting tasks first, then CPU-heavy work.")
    show_concurrency()
    show_parallelism()
    print_section("Takeaway")
    print("  Sync:        the caller waits until the operation finishes.")
    print("  Async:       the task yields while waiting, letting other tasks make progress.")
    print("  Concurrency: one worker manages multiple tasks in the same period.")
    print("  Parallelism: multiple workers execute calculations at the same instant.")
    print("\n  Sync/async describes control flow; concurrency/parallelism describes execution.")
    print("\n  sleep() leaves the CPU idle; counting primes keeps a CPU core busy.\n")


if __name__ == "__main__":
    main()
