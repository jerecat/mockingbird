from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from regorch.contracts import ExecutionAdapter
from regorch.models import Job, JobExecution, TestResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Adapter(ExecutionAdapter):
    """Demo adapter that connects regorch to its own pytest suite.

    This is intentionally concrete and lives outside core. It demonstrates
    that the orchestrator can schedule and collect its own repository tests
    using exactly the same extension boundary as a real verification project.
    """

    def setup(self, context):
        Path(context["paths"]["adapter_workdir"]).mkdir(parents=True, exist_ok=True)

    def plan(self, context):
        suites = context["execution"].get("config", {}).get("suites", [])
        return [
            Job(
                id=str(item["id"]),
                payload={"targets": list(item["targets"])},
                metadata=dict(item.get("metadata", {})),
            )
            for item in suites
        ]

    def execute(self, context, job):
        started_at = _now()
        started = time.monotonic()
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *list(job.payload["targets"]),
        ]
        completed = subprocess.run(
            command,
            cwd=context["invocation_dir"],
            text=True,
            capture_output=True,
        )
        return JobExecution(
            job_id=job.id,
            started_at=started_at,
            finished_at=_now(),
            duration_s=time.monotonic() - started,
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
            reason = None
            if returncode != 0:
                stderr = str(execution.observation.get("stderr", "")).strip()
                stdout = str(execution.observation.get("stdout", "")).strip()
                tail = (stderr or stdout)[-500:]
                reason = f"pytest exit={returncode}" + (f": {tail}" if tail else "")
            results.append(
                TestResult(
                    id=execution.job_id,
                    status="PASS" if returncode == 0 else "FAIL",
                    duration_s=execution.duration_s,
                    reason=reason,
                )
            )
        return results
