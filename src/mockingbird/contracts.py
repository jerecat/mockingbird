from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .models import CollectionAttempt, CheckResult, ExecutionContext, Job, JobExecution, TestResult


class ExecutionAdapter(ABC):
    """Project-specific execution boundary."""

    def probe(self, context: dict[str, Any]) -> list[CheckResult]:
        return [
            CheckResult(
                component="execution",
                name="probe",
                status="WARN",
                message="adapter does not implement a project-specific connection probe",
            )
        ]

    def export_jobs(self, jobs: list[dict[str, Any]]) -> dict[str, Any]:
        """Return an execution YAML contract for resolved saved Jobs."""
        raise ValueError("execution adapter does not support saving resolved Jobs")

    @abstractmethod
    def setup(self, context: dict[str, Any]) -> None: ...

    @abstractmethod
    def plan(self, context: dict[str, Any]) -> list[Job]: ...

    @abstractmethod
    def execute(
        self,
        context: dict[str, Any],
        job: Job,
        execution: ExecutionContext,
    ) -> JobExecution: ...

    @abstractmethod
    def collect(
        self, context: dict[str, Any], executions: list[JobExecution]
    ) -> list[TestResult | CollectionAttempt]: ...


class CapacityProvider(ABC):
    """Reports current capacity available to Mockingbird dispatch.

    Core reserves in-flight execute calls against this value. Providers for
    asynchronous external systems must account for already handed-off work in
    later samples; core deliberately does not track external scheduler job IDs.
    """

    def bind_context(self, context: dict[str, Any]) -> None:
        """Optional context binding; existing custom providers need no changes."""

    def probe(self) -> list[CheckResult]:
        try:
            slots = self.available_slots()
        except Exception as exc:
            return [
                CheckResult(
                    component="capacity",
                    name="available_slots",
                    status="FAIL",
                    message=f"{type(exc).__name__}: {exc}",
                )
            ]
        return [
            CheckResult(
                component="capacity",
                name="available_slots",
                status="PASS",
                message=f"available_slots={slots}",
                details={"available_slots": slots},
            )
        ]

    @abstractmethod
    def available_slots(self) -> int: ...


class SourceProvider(ABC):
    """Materializes one source without exposing source-control semantics to core."""

    def probe(self, source: dict[str, Any]) -> list[CheckResult]:
        return [
            CheckResult(
                component=f"source:{source.get('name', '?')}",
                name="probe",
                status="WARN",
                message="source provider does not implement a connection probe",
            )
        ]

    def export_source(self, source, prepared, observation):
        """Optionally pin an exported source in place; return limitations."""
        return [f"source {source['name']!r}: provider cannot pin run-time state; original settings retained"]

    def observe(self, source: dict[str, Any]) -> dict[str, Any] | None:
        """Optional read-only run-start evidence; None means unsupported."""
        return None

    @abstractmethod
    def materialize(
        self, source: dict[str, Any], destination: Path
    ) -> dict[str, Any]: ...

