from __future__ import annotations

from pathlib import Path

from mockingbird.context import load_definition
from mockingbird.doctor import doctor_failed, run_doctor


def test_doctor_checks_linux_sanity_without_preparing_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    definition = tmp_path / "regression.yaml"
    definition.write_text(
        """
plan: doctor-demo
sources: []
execution:
  adapter: demo_linux
  config:
    tests:
      - id: list
        command: [ls, -la]
scheduler:
  capacity_provider: fixed
  max_parallel: 1
  poll_interval_s: 0.1
  config: {slots: 2}
"""
    )
    checks = run_doctor(load_definition(definition))
    assert doctor_failed(checks) is False
    assert any(item.component == "execution" and item.status == "PASS" for item in checks)
    assert any(item.component == "capacity" and item.status == "PASS" for item in checks)
    assert not (tmp_path / "work" / ".reg" / "context.json").exists()


def test_doctor_reports_missing_execution_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    definition = tmp_path / "regression.yaml"
    definition.write_text(
        """
plan: doctor-missing
sources: []
execution:
  adapter: demo_linux
  config:
    tests:
      - id: missing
        command: [definitely-not-a-real-mockingbird-command]
scheduler:
  capacity_provider: fixed
  config: {slots: 1}
"""
    )
    checks = run_doctor(load_definition(definition))
    assert doctor_failed(checks) is True
    assert any(item.status == "FAIL" and "not found" in item.message for item in checks)


def test_doctor_accepts_declarative_command_contract_without_project_python(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = tmp_path / "run.sh"
    runner.write_text("#!/bin/sh\nexit 0\n")
    runner.chmod(0o755)

    definition = tmp_path / "regression.yaml"
    definition.write_text(
        """
plan: declarative-doctor
sources: []
execution:
  command: ["./run.sh"]
  timeout_s: 5
  jobs: [smoke]
  collect:
    mode: no-check
scheduler:
  capacity_provider: fixed
  max_parallel: 1
  poll_interval_s: 0.1
  config: {slots: 1}
"""
    )

    checks = run_doctor(load_definition(definition))

    assert doctor_failed(checks) is False
    assert any(
        item.component == "execution"
        and item.name == "plugin"
        and item.message == "command"
        and item.status == "PASS"
        for item in checks
    )
    assert not (tmp_path / "work" / ".reg" / "context.json").exists()
