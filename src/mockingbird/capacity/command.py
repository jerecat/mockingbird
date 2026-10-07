from __future__ import annotations

import subprocess
from typing import Any

from mockingbird.contracts import CapacityProvider
from mockingbird.models import CheckResult
from mockingbird.validation import positive_seconds


class Provider(CapacityProvider):
    """Runs a command whose stdout is the current Mockingbird dispatch allowance.

    For asynchronous external systems, the wrapper owns accounting for work
    already handed off outside Mockingbird.
    """

    def __init__(self, config: dict[str, Any]):
        command = config.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(item, str) for item in command
        ):
            raise ValueError("capacity command must be a non-empty list of strings")
        self._command = command
        self._timeout_s = positive_seconds(config.get("timeout_s", 10.0), "capacity timeout_s")

    def probe(self):
        try:
            slots = self.available_slots()
        except Exception as exc:
            return [
                CheckResult(
                    component="capacity",
                    name="command",
                    status="FAIL",
                    message=f"{type(exc).__name__}: {exc}",
                )
            ]
        return [
            CheckResult(
                component="capacity",
                name="command",
                status="PASS",
                message=f"capacity command returned {slots}",
                details={"available_slots": slots},
            )
        ]

    def available_slots(self) -> int:
        completed = subprocess.run(
            self._command,
            check=True,
            text=True,
            capture_output=True,
            timeout=self._timeout_s,
        )
        text = completed.stdout.strip()
        try:
            slots = int(text)
        except ValueError as exc:
            raise RuntimeError(
                f"capacity command must print one integer, got {text!r}"
            ) from exc
        if slots < 0:
            raise RuntimeError(f"capacity command returned negative slots: {slots}")
        return slots
