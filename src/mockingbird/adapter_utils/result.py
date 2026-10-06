from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from mockingbird.models import JobExecution, TestResult


def result_from_execution(
    execution: JobExecution,
    status: str,
    *,
    artifacts: Iterable[str] = (),
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TestResult:
    """Carry Mockingbird execution identity into a collected result."""
    return TestResult(
        id=execution.job_id,
        status=status,
        duration_s=execution.duration_s,
        reason=reason,
        metadata={} if metadata is None else dict(metadata),
        artifacts=list(artifacts),
    )


def execution_path_refs(execution: JobExecution, *names: str) -> list[str]:
    """Return selected generic execution path references when present."""
    return [value for name in names if (value := execution.paths.get(name)) is not None]
