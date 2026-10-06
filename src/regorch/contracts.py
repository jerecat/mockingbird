from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .models import Job, JobExecution, TestResult


class ExecutionAdapter(ABC):
    """Project-specific execution boundary."""

    @abstractmethod
    def setup(self, context: dict[str, Any]) -> None: ...

    @abstractmethod
    def plan(self, context: dict[str, Any]) -> list[Job]: ...

    @abstractmethod
    def execute(self, context: dict[str, Any], job: Job) -> JobExecution: ...

    @abstractmethod
    def collect(
        self, context: dict[str, Any], executions: list[JobExecution]
    ) -> list[TestResult]: ...


class CapacityProvider(ABC):
    """Reports the total concurrent-job allowance at this moment."""

    @abstractmethod
    def available_slots(self) -> int: ...


class SourceProvider(ABC):
    """Materializes one source without exposing source-control semantics to core."""

    @abstractmethod
    def materialize(
        self, source: dict[str, Any], destination: Path
    ) -> dict[str, Any]: ...
