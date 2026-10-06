from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

from mockingbird.adapter_utils import run_process
from mockingbird.contracts import ExecutionAdapter
from mockingbird.models import CheckResult, ExecutionContext, Job, JobExecution, TestResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Adapter(ExecutionAdapter):
    """Demo adapter that connects mockingbird to its own pytest suite."""

    def probe(self, context):
        available = importlib.util.find_spec("pytest") is not None
        return [
            CheckResult(
                component="execution",
                name="pytest",
                status="PASS" if available else "FAIL",
                message="pytest importable" if available else "pytest is not installed",
            )
        ]

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

    def execute(self, context, job, execution: ExecutionContext):
        started_at = _now()
        process = run_process(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                *list(job.payload["targets"]),
            ],
            execution,
            cwd=context["invocation_dir"],
            timeout_s=float(job.payload.get("timeout_s", 120.0)),
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
                reason = "pytest timeout"
            else:
                status = "PASS" if returncode == 0 else "FAIL"
                reason = None if returncode == 0 else f"pytest exit={returncode}"
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
                    artifacts=[
                        path
                        for path in (
                            execution.paths.get("stdout"),
                            execution.paths.get("stderr"),
                        )
                        if path is not None
                    ],
                )
            )
        return results
