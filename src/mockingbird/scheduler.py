from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable

from .models import Job, JobExecution


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
    pending = list(jobs)
    running = set()
    results: list[JobExecution] = []

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        while pending or running:
            external_limit = max(0, int(capacity.available_slots()))
            allowed_running = min(max_parallel, external_limit)
            submissions = min(
                max(0, allowed_running - len(running)),
                len(pending),
            )

            for _ in range(submissions):
                job = pending.pop(0)
                running.add(pool.submit(execute, job))

            if running:
                done, not_done = wait(
                    running,
                    timeout=poll_interval_s,
                    return_when=FIRST_COMPLETED,
                )
                running = not_done
                results.extend(future.result() for future in done)
            elif pending:
                time.sleep(poll_interval_s)

    by_id = {execution.job_id: execution for execution in results}
    return [by_id[job.id] for job in jobs]
