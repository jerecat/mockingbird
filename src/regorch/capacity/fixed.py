from __future__ import annotations

from typing import Any

from regorch.contracts import CapacityProvider
from regorch.models import CheckResult


class Provider(CapacityProvider):
    def __init__(self, config: dict[str, Any]):
        self._slots = int(config.get("slots", 1))
        if self._slots < 0:
            raise ValueError("capacity slots must be >= 0")

    def probe(self):
        return [
            CheckResult(
                component="capacity",
                name="fixed",
                status="PASS",
                message=f"configured slots={self._slots}",
                details={"available_slots": self._slots},
            )
        ]

    def available_slots(self) -> int:
        return self._slots
