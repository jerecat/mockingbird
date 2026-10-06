from __future__ import annotations

from typing import Any

from regorch.contracts import CapacityProvider


class Provider(CapacityProvider):
    def __init__(self, config: dict[str, Any]):
        self._slots = int(config.get("slots", 1))
        if self._slots < 0:
            raise ValueError("capacity slots must be >= 0")

    def available_slots(self) -> int:
        return self._slots
