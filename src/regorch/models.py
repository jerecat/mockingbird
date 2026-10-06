from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Job:
    """A canonical schedulable unit. payload is deliberately opaque to core."""

    id: str
    payload: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobExecution:
    """Execution evidence. observation is interpreted only by the adapter."""

    job_id: str
    started_at: str
    finished_at: str
    duration_s: float
    observation: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestResult:
    id: str
    status: str
    duration_s: float | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
