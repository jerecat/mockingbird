from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .models import Job, JobExecution
from .validation import capacity_slots, positive_seconds


def validate_max_parallel(value) -> None:
    """ADR 0009: only an explicit integer 1 enables execution."""
    if type(value) is not int or value != 1:
        raise ValueError("scheduler.max_parallel must be the integer 1; parallel execution is disabled")


def run_jobs(
    jobs: list[Job],
    execute: Callable[[Job], JobExecution],
    capacity,
    max_parallel: int,
    poll_interval_s: float,
) -> list[JobExecution]:
    """Run jobs under a hard local cap and the latest reported capacity.

    At every scheduling decision, in-flight execute calls are reserved against
    both max_parallel and capacity.available_slots(). If reported capacity drops
    below the number already running, existing calls are left alone and no new
    calls are dispatched.

    For asynchronous external hand-off, the CapacityProvider must account for
    work already handed to that external system on later samples. Core does not
    track external scheduler job IDs.
    """

    validate_max_parallel(max_parallel)
    positive_seconds(poll_interval_s, "scheduler.poll_interval_s")
    results: list[JobExecution] = []
    # One worker is intentional: SIGINT stops dispatch in the main thread,
    # while context-manager shutdown drains the current Job and its evidence.
    with ThreadPoolExecutor(max_workers=1) as pool:
        for job in jobs:
            while capacity_slots(capacity.available_slots()) == 0:
                time.sleep(poll_interval_s)
            results.append(pool.submit(execute, job).result())
    return results
