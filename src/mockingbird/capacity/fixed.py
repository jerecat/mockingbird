from __future__ import annotations

from typing import Any

from mockingbird.contracts import CapacityProvider
from mockingbird.models import CheckResult
from mockingbird.validation import capacity_slots


class Provider(CapacityProvider):
    def __init__(self, config: dict[str, Any]):
        self._slots = capacity_slots(config.get("slots", 1))

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
