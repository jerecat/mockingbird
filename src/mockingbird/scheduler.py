from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable

from .models import Job, JobExecution


def run_jobs(
    jobs: list[Job],
    execute: Callable[[Job], JobExecution],
    capacity,
    max_parallel: int,
    poll_interval_s: float,
) -> list[JobExecution]:
    """Run jobs under a local hard cap and a polled external capacity limit.

    ``capacity.available_slots()`` is intentionally generic. It returns the
    maximum number of this orchestrator's jobs that may be concurrently
    running *right now*. If the value drops below the number already running,
    existing jobs are left alone and no new jobs are submitted.
    """

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
