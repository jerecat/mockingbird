from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from regorch.models import Job, JobExecution
from regorch.scheduler import run_jobs


class FixedCapacity:
    def __init__(self, value: int):
        self.value = value
        self.calls = 0

    def available_slots(self) -> int:
        self.calls += 1
        return self.value


class SequenceCapacity:
    def __init__(self, values: list[int]):
        self.values = list(values)
        self.calls = 0

    def available_slots(self) -> int:
        index = min(self.calls, len(self.values) - 1)
        self.calls += 1
        return self.values[index]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_scheduler_respects_external_capacity_and_local_cap():
    jobs = [Job(id=f"job{i}") for i in range(6)]
    lock = threading.Lock()
    running = 0
    peak = 0

    def execute(job: Job) -> JobExecution:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        start = time.monotonic()
        time.sleep(0.03)
        with lock:
            running -= 1
        return JobExecution(job.id, _now(), _now(), time.monotonic() - start)

    result = run_jobs(
        jobs,
        execute,
        FixedCapacity(2),
        max_parallel=4,
        poll_interval_s=0.005,
    )

    assert [item.job_id for item in result] == [job.id for job in jobs]
    assert peak == 2


def test_scheduler_polls_until_capacity_becomes_available():
    jobs = [Job(id="one")]
    capacity = SequenceCapacity([0, 0, 1])

    result = run_jobs(
        jobs,
        lambda job: JobExecution(job.id, _now(), _now(), 0.0),
        capacity,
        max_parallel=3,
        poll_interval_s=0.001,
    )

    assert [item.job_id for item in result] == ["one"]
    assert capacity.calls >= 3
