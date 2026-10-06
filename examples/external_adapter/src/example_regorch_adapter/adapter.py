from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone

from regorch.contracts import ExecutionAdapter
from regorch.models import Job, JobExecution, TestResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Adapter(ExecutionAdapter):
    """Minimal example of a project-owned adapter installed outside regorch."""

    def setup(self, context):
        pass

    def plan(self, context):
        tests = context["execution"].get("config", {}).get("tests", [])
        return [Job(id=str(test["id"]), payload=dict(test)) for test in tests]

    def execute(self, context, job):
        started_at = _now()
        started = time.monotonic()
        completed = subprocess.run(
            list(job.payload["command"]),
            cwd=context["paths"]["adapter_workdir"],
            text=True,
            capture_output=True,
        )
        return JobExecution(
            job_id=job.id,
            started_at=started_at,
            finished_at=_now(),
            duration_s=time.monotonic() - started,
            observation={"returncode": completed.returncode},
        )

    def collect(self, context, executions):
        return [
            TestResult(
                id=item.job_id,
                status="PASS" if item.observation["returncode"] == 0 else "FAIL",
                duration_s=item.duration_s,
            )
            for item in executions
        ]
