"""Concise diagnostics must not hide failures or overstate probe coverage."""
from mockingbird.cli import _doctor_summary
from mockingbird.models import CheckResult


def test_success_groups_repeated_executables(capsys):
    checks = [CheckResult("configuration", "definition", "PASS", "valid"),
              CheckResult("execution", "plugin", "PASS", "command")]
    checks += [CheckResult("execution", f"job_{i}:collect-command", "PASS", "/venv/bin/python3") for i in range(8)]
    checks += [CheckResult("capacity", "fixed", "PASS", "configured slots=1", {"available_slots": 1})]
    _doctor_summary(checks)
    text = capsys.readouterr().out
    assert "Pre-run checks: OK" in text and "1 configured slot" in text
    assert "No Jobs executed" in text and "one Job at a time" in text
    assert "/venv/bin/python3" not in text and "plugin" not in text and "job_0" not in text
    _doctor_summary(checks, details=True)
    text = capsys.readouterr().out
    assert text.count("/venv/bin/python3") == 8
    lines = [line for line in text.splitlines() if "/venv/bin/python3" in line]
    assert len({line.index("/venv/bin/python3") for line in lines}) == 1


def test_failure_and_warning_are_visible_without_details(capsys):
    _doctor_summary([
        CheckResult("execution", "very_long_job:command", "FAIL", "command not found: missing-tool\nCheck PATH"),
        CheckResult("source:design", "probe", "WARN", "probe not implemented"),
    ])
    text = capsys.readouterr().out
    assert "Pre-run checks: FAILED" in text
    for phrase in ("very_long_job:command", "missing-tool", "Check PATH", "probe not implemented", "doctor again"):
        assert phrase in text
    assert "Run order" not in text


def test_warning_is_not_reported_as_all_ok(capsys):
    _doctor_summary([CheckResult("execution", "probe", "WARN", "not implemented")])
    text = capsys.readouterr().out
    assert "Pre-run checks: ATTENTION" in text and "not implemented" in text


def test_zero_capacity_explains_waiting(capsys):
    _doctor_summary([CheckResult("capacity", "fixed", "PASS", "configured slots=0",
                                {"available_slots": 0})])
    text = capsys.readouterr().out
    assert "0 configured slots" in text and "dispatch will wait" in text
