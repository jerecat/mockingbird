from __future__ import annotations

import sys

import pytest

from regorch.capacity.command import Provider


def test_command_capacity_provider_reads_one_integer():
    provider = Provider(
        {"command": [sys.executable, "-c", "print(3)"], "timeout_s": 2}
    )
    assert provider.available_slots() == 3


def test_command_capacity_provider_rejects_non_integer():
    provider = Provider(
        {"command": [sys.executable, "-c", "print('busy')"], "timeout_s": 2}
    )
    with pytest.raises(RuntimeError, match="one integer"):
        provider.available_slots()
