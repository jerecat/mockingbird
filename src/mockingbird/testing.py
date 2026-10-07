from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import CapacityProvider, ExecutionAdapter, SourceProvider
from .models import CollectionAttempt, CheckResult, ExecutionContext, JobExecution
from .validation import bind_execution, capacity_slots, validate_jobs, validate_outcome


def _result(component: str, name: str, fn) -> CheckResult:
    try:
        message, details = fn()
        return CheckResult(component, name, "PASS", message, details)
    except Exception as exc:
        return CheckResult(component, name, "FAIL", f"{type(exc).__name__}: {exc}")


def _assert_json(value: Any) -> None:
    json.dumps(value, allow_nan=False)


def make_execution_context(root: str | Path, job_id: str = "conformance") -> ExecutionContext:
    root = Path(root).resolve()
    job_dir = root / "job"
    workdir = job_dir / "work"
    artifact_dir = job_dir / "artifacts"
    logs_dir = job_dir / "logs"
    for path in (job_dir, workdir, artifact_dir, logs_dir):
        path.mkdir(parents=True, exist_ok=True)
    return ExecutionContext(
        run_id="conformance",
        run_dir=str(root),
        job_dir=str(job_dir),
        workdir=str(workdir),
        artifact_dir=str(artifact_dir),
        logs_dir=str(logs_dir),
        stdout_path=str(logs_dir / "stdout.log"),
        stderr_path=str(logs_dir / "stderr.log"),
    )


def check_execution_adapter(
    adapter: ExecutionAdapter,
    context: dict[str, Any],
    root: str | Path,
    *,
    exercise_execute: bool = True,
) -> list[CheckResult]:
    """Exercise the public adapter contract without knowing project semantics."""

    checks: list[CheckResult] = []
    checks.extend(adapter.probe(context))

    def setup_twice():
        adapter.setup(context)
        adapter.setup(context)
        return "setup completed twice", {}

    checks.append(_result("execution", "setup-idempotence", setup_twice))

    first_jobs = []
    second_jobs = []

    def plan_contract():
        nonlocal first_jobs, second_jobs
        first_jobs = adapter.plan(context)
        second_jobs = adapter.plan(context)
        validate_jobs(first_jobs)
        validate_jobs(second_jobs)
        ids = [job.id for job in first_jobs]
        ids2 = [job.id for job in second_jobs]
        if ids != ids2:
            raise AssertionError("job IDs changed between two plan() calls under the same context")
        return f"plan stable with {len(ids)} job(s)", {"job_ids": ids}

    checks.append(_result("execution", "plan-contract", plan_contract))

    if exercise_execute and first_jobs:
        sample = first_jobs[0]
        execution_context = make_execution_context(Path(root) / "execution", sample.id)
        captured: JobExecution | None = None

        def execute_contract():
            nonlocal captured
            captured = adapter.execute(context, sample, execution_context)
            bind_execution(captured, sample, execution_context)
            _assert_json(captured.to_dict())
            return "sample execute returned serializable JobExecution", {}

        checks.append(_result("execution", "execute-contract", execute_contract))

        def collect_contract():
            if captured is None:
                raise AssertionError("sample execute did not complete")
            results = adapter.collect(context, [captured])
            if len(results) != 1 or results[0].id != sample.id:
                raise AssertionError("collect must return exactly one result for the sample execution")
            validate_outcome(results[0], sample.id)
            if isinstance(results[0], CollectionAttempt):
                return "sample collect returned unresolved state", {"state": results[0].state}
            status = str(results[0].status).upper()
            return f"sample collect returned {status}", {"status": status}

        checks.append(_result("execution", "collect-contract", collect_contract))

    return checks


def check_source_provider(
    provider: SourceProvider,
    source: dict[str, Any],
    destination: str | Path,
) -> list[CheckResult]:
    checks = list(provider.probe(source))

    def materialize_contract():
        evidence = provider.materialize(source, Path(destination))
        if not isinstance(evidence, dict):
            raise AssertionError("materialize must return a mapping")
        if not evidence.get("resolved_revision"):
            raise AssertionError("materialize evidence must include resolved_revision")
        _assert_json(evidence)
        return "materialize returned serializable resolved evidence", evidence

    checks.append(_result(f"source:{source.get('name', '?')}", "materialize-contract", materialize_contract))
    return checks


def check_capacity_provider(provider: CapacityProvider) -> list[CheckResult]:
    checks = list(provider.probe())

    def capacity_contract():
        values = [provider.available_slots(), provider.available_slots()]
        for value in values:
            capacity_slots(value)
        return f"two valid capacity samples: {values}", {"samples": values}

    checks.append(_result("capacity", "contract", capacity_contract))
    return checks


def assert_conformance(checks: list[CheckResult]) -> None:
    failures = [item for item in checks if item.status.upper() == "FAIL"]
    if failures:
        details = "; ".join(f"{item.component}/{item.name}: {item.message}" for item in failures)
        raise AssertionError(details)
