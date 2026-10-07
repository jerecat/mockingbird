from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Job:
    """A canonical schedulable unit. payload is deliberately opaque to core."""

    id: str
    payload: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionContext:
    """Generic per-job filesystem context created by core.

    The adapter owns what happens inside these directories. Core owns only
    their allocation and evidence-friendly naming.
    """

    run_id: str
    run_dir: str
    job_dir: str
    workdir: str
    artifact_dir: str
    logs_dir: str
    stdout_path: str
    stderr_path: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def evidence_paths(self) -> dict[str, str]:
        root = Path(self.run_dir)
        return {
            key: str(Path(value).relative_to(root))
            for key, value in {
                "job_dir": self.job_dir,
                "workdir": self.workdir,
                "artifact_dir": self.artifact_dir,
                "logs_dir": self.logs_dir,
                "stdout": self.stdout_path,
                "stderr": self.stderr_path,
            }.items()
        }


@dataclass
class JobExecution:
    """Execution evidence. observation is interpreted only by the adapter."""

    job_id: str
    started_at: str
    finished_at: str
    duration_s: float
    observation: Any = None
    paths: dict[str, str] = field(default_factory=dict)

    contract: dict[str, Any] = field(default_factory=dict)
    run_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestResult:
    id: str
    status: str
    duration_s: float | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CheckResult:
    component: str
    name: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CollectionAttempt:
    """Unresolved collection state, deliberately separate from TestResult."""

    id: str
    state: str  # PENDING or ERROR; neither is a final test judgement.
    reason: str | None = None
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
