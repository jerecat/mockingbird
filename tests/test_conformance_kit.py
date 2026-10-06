from __future__ import annotations

from pathlib import Path

import pytest

from mockingbird.adapters.demo_linux import Adapter
from mockingbird.capacity.fixed import Provider as FixedCapacity
from mockingbird.context import load_definition, provisional_context
from mockingbird.contracts import SourceProvider
from mockingbird.models import CheckResult
from mockingbird.testing import (
    assert_conformance,
    check_capacity_provider,
    check_execution_adapter,
    check_source_provider,
)


class FakeSource(SourceProvider):
    def probe(self, source):
        return [CheckResult(f"source:{source['name']}", "probe", "PASS", "ok")]

    def materialize(self, source, destination: Path):
        destination.mkdir(parents=True, exist_ok=True)
        return {"resolved_revision": "abc123", "provider_metadata": {}}


def _definition(tmp_path: Path) -> Path:
    path = tmp_path / "regression.yaml"
    path.write_text(
        """
name: conformance
sources: []
execution:
  adapter: demo_linux
  config:
    tests:
      - id: echo-test
        command: [sh, -c, 'echo hello']
scheduler:
  capacity_provider: fixed
  max_parallel: 1
  poll_interval_s: 0.1
  config: {slots: 1}
"""
    )
    return path


def test_execution_adapter_conformance_kit_exercises_connection_and_sample(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = provisional_context(load_definition(_definition(tmp_path)))
    checks = check_execution_adapter(Adapter(), context, tmp_path / "contract")
    assert_conformance(checks)
    assert {item.name for item in checks} >= {
        "setup-idempotence", "plan-contract", "execute-contract", "collect-contract"
    }


def test_source_and_capacity_conformance_kits(tmp_path):
    source_checks = check_source_provider(
        FakeSource(),
        {"name": "dut", "provider": "fake", "url": "unused", "revision": "x"},
        tmp_path / "source",
    )
    capacity_checks = check_capacity_provider(FixedCapacity({"slots": 3}))
    assert_conformance(source_checks)
    assert_conformance(capacity_checks)


def test_assert_conformance_surfaces_adapter_failures():
    with pytest.raises(AssertionError, match="bad"):
        assert_conformance([CheckResult("execution", "bad", "FAIL", "bad thing")])
