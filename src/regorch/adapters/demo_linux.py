from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from regorch.contracts import ExecutionAdapter
from regorch.models import Job, JobExecution, TestResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Adapter(ExecutionAdapter):
    """Demo adapter. Command semantics intentionally stop at this boundary."""

    def setup(self, context):
        Path(context["paths"]["adapter_workdir"]).mkdir(parents=True, exist_ok=True)

    def plan(self, context):
        tests = context["execution"].get("config", {}).get("tests", [])
        jobs = []
        for item in tests:
            jobs.append(
                Job(
                    id=str(item["id"]),
                    payload={"command": list(item["command"])},
                    metadata=dict(item.get("metadata", {})),
                )
            )
        return jobs

    def execute(self, context, job):
        started_at = _now()
        start = time.monotonic()
        command = list(job.payload["command"])
        completed = subprocess.run(
            command,
            cwd=context["paths"]["adapter_workdir"],
            text=True,
            capture_output=True,
        )
        duration_s = time.monotonic() - start
        return JobExecution(
            job_id=job.id,
            started_at=started_at,
            finished_at=_now(),
            duration_s=duration_s,
            observation={
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )

    def collect(self, context, executions):
        results = []
        for execution in executions:
            returncode = int(execution.observation["returncode"])
            results.append(
                TestResult(
                    id=execution.job_id,
                    status="PASS" if returncode == 0 else "FAIL",
                    duration_s=execution.duration_s,
                    reason=None if returncode == 0 else f"exit={returncode}",
                )
            )
        return results
