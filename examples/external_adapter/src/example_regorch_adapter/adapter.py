from __future__ import annotations

import shutil
from datetime import datetime, timezone

from regorch.adapter_utils import run_process
from regorch.contracts import ExecutionAdapter
from regorch.models import CheckResult, ExecutionContext, Job, JobExecution, TestResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Adapter(ExecutionAdapter):
    """Minimal example of a project-owned adapter installed outside regorch."""

    def probe(self, context):
        commands = sorted({
            str(item["command"][0])
            for item in context["execution"].get("config", {}).get("tests", [])
            if item.get("command")
        })
        return [
            CheckResult(
                "execution",
                f"command:{command}",
                "PASS" if shutil.which(command) else "FAIL",
                shutil.which(command) or "command not found",
            )
            for command in commands
        ]

    def setup(self, context):
        pass

    def plan(self, context):
        tests = context["execution"].get("config", {}).get("tests", [])
        return [Job(id=str(test["id"]), payload=dict(test)) for test in tests]

    def execute(self, context, job, execution: ExecutionContext):
        started_at = _now()
        process = run_process(
            list(job.payload["command"]),
            execution,
            timeout_s=float(job.payload.get("timeout_s", 30.0)),
        )
        return JobExecution(
            job_id=job.id,
            started_at=started_at,
            finished_at=_now(),
            duration_s=process.duration_s,
            observation=process.to_observation(),
        )

    def collect(self, context, executions):
        results = []
        for item in executions:
            timed_out = bool(item.observation.get("timed_out", False))
            rc = int(item.observation["returncode"])
            results.append(
                TestResult(
                    id=item.job_id,
                    status="ERROR" if timed_out else ("PASS" if rc == 0 else "FAIL"),
                    duration_s=item.duration_s,
                    reason="timeout" if timed_out else (None if rc == 0 else f"exit={rc}"),
                    metadata={"stdout": item.paths.get("stdout"), "stderr": item.paths.get("stderr")},
                )
            )
        return results
