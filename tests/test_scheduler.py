from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from mockingbird.models import Job, JobExecution
from mockingbird.scheduler import run_jobs


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


class MutableCapacity:
    def __init__(self, value: int):
        self.value = value

    def available_slots(self) -> int:
        return self.value


def test_capacity_drop_to_zero_blocks_new_dispatch_without_killing_running_job():
    jobs = [Job(id=f"job{i}") for i in range(3)]
    capacity = MutableCapacity(1)
    first_started = threading.Event()
    release_first = threading.Event()
    started: list[str] = []
    result: list[JobExecution] = []

    def execute(job: Job) -> JobExecution:
        started.append(job.id)
        if job.id == "job0":
            first_started.set()
            assert release_first.wait(timeout=1.0)
        return JobExecution(job.id, _now(), _now(), 0.0)

    def runner():
        result.extend(
            run_jobs(
                jobs,
                execute,
                capacity,
                max_parallel=8,
                poll_interval_s=0.002,
            )
        )

    thread = threading.Thread(target=runner)
    thread.start()
    assert first_started.wait(timeout=1.0)

    capacity.value = 0
    release_first.set()
    time.sleep(0.03)
    assert started == ["job0"]

    capacity.value = 1
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    assert [item.job_id for item in result] == [job.id for job in jobs]
