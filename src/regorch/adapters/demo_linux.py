from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from regorch.adapter_utils import run_process
from regorch.contracts import ExecutionAdapter
from regorch.models import CheckResult, ExecutionContext, Job, JobExecution, TestResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Adapter(ExecutionAdapter):
    """Demo adapter. Command semantics intentionally stop at this boundary."""

    def probe(self, context):
        checks: list[CheckResult] = []
        tests = context["execution"].get("config", {}).get("tests", [])
        commands = sorted({str(item["command"][0]) for item in tests if item.get("command")})
        for command in commands:
            resolved = shutil.which(command)
            checks.append(
                CheckResult(
                    component="execution",
                    name=f"command:{command}",
                    status="PASS" if resolved else "FAIL",
                    message=resolved or "command not found on PATH",
                )
            )
        return checks or [
            CheckResult("execution", "commands", "WARN", "no demo commands configured")
        ]

    def setup(self, context):
        Path(context["paths"]["adapter_workdir"]).mkdir(parents=True, exist_ok=True)

    def plan(self, context):
        tests = context["execution"].get("config", {}).get("tests", [])
        return [
            Job(
                id=str(item["id"]),
                payload={"command": list(item["command"])},
                metadata=dict(item.get("metadata", {})),
            )
            for item in tests
        ]

    def execute(self, context, job, execution: ExecutionContext):
        started_at = _now()
        timeout_s = job.payload.get("timeout_s")
        process = run_process(
            list(job.payload["command"]),
            execution,
            timeout_s=None if timeout_s is None else float(timeout_s),
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
        for execution in executions:
            observation = execution.observation
            returncode = int(observation["returncode"])
            timed_out = bool(observation.get("timed_out", False))
            if timed_out:
                status = "ERROR"
                reason = "timeout"
            else:
                status = "PASS" if returncode == 0 else "FAIL"
                reason = None if returncode == 0 else f"exit={returncode}"
            results.append(
                TestResult(
                    id=execution.job_id,
                    status=status,
                    duration_s=execution.duration_s,
                    reason=reason,
                    metadata={
                        "stdout": execution.paths.get("stdout"),
                        "stderr": execution.paths.get("stderr"),
                    },
                )
            )
        return results
