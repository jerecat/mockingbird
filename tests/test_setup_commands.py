"""Setup has its own synchronous contract and preserves failed attempts."""
import json
from pathlib import Path
import sys

import pytest
import yaml

from mockingbird import lifecycle
from mockingbird.context import load_definition, prepare, metadata_path, load_state
from mockingbird.setup_contract import resolve_setup
from mockingbird.doctor import run_doctor, doctor_failed


def definition(tmp_path, monkeypatch, jobs=None):
    monkeypatch.chdir(tmp_path)
    data = {"execution": {"command": [sys.executable, "-c", "pass"], "args": [],
                          "timeout_s": 2, "jobs": ["test"]},
            "scheduler": {"capacity_provider": "fixed"}}
    if jobs is not None:
        data["setup"] = {"defaults": {"timeout_s": 2, "args": []}, "jobs": jobs}
    path = tmp_path / "regression.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_definition(path)


def read(path):
    return json.loads(path.read_text())


def test_fail_edit_retry_then_failed_rerun_blocks_old_plan(tmp_path, monkeypatch):
    script = tmp_path / "prepare.py"
    script.write_text("print('broken setup'); raise SystemExit(7)")
    first = {"id": "first", "command": [sys.executable, "-c",
             "from pathlib import Path; p=Path('calls'); p.write_text(p.read_text()+'x' if p.exists() else 'x')"]}
    second = {"id": "build", "command": [sys.executable, str(script)]}
    third = {"id": "last", "command": [sys.executable, "-c", "from pathlib import Path; Path('last').touch()"]}
    d = definition(tmp_path, monkeypatch, [first, second, third])
    prepare(d)
    with pytest.raises(RuntimeError, match="setup"):
        lifecycle.create_plan(d)
    with pytest.raises(RuntimeError, match="exit=7"):
        lifecycle.setup(d)
    failed = Path(load_state(d)["last_setup_dir"])
    assert read(failed / "setup.json")["completed"] == ["first"]
    assert not (tmp_path / "last").exists()
    logs = list(failed.glob("jobs/*/logs/stdout.log"))
    assert any("broken setup" in p.read_text() for p in logs)
    original = {p.relative_to(failed): p.read_bytes() for p in failed.rglob('*') if p.is_file()}
    script.write_text("print('fixed setup')")  # no prepare: only script contents changed
    success = lifecycle.setup(d)
    assert success != failed and read(success / "setup.json")["status"] == "SUCCEEDED"
    assert (tmp_path / "calls").read_text() == "xx"  # restart from first Job
    assert (tmp_path / "last").exists()
    assert all((failed / p).read_bytes() == content for p, content in original.items())
    lifecycle.create_plan(d)
    old_plan = (metadata_path(d) / "plan.json").read_bytes()
    _, existing_run, _ = lifecycle.run(d)
    script.write_text("raise SystemExit(9)")
    with pytest.raises(RuntimeError, match="exit=9"):
        lifecycle.setup(d)
    assert lifecycle.collect(d, existing_run)[0]["status"] == "PASS"
    assert not (metadata_path(d) / "plan.json").exists()
    (metadata_path(d) / "plan.json").write_bytes(old_plan)
    for operation in (lifecycle.create_plan, lifecycle.run):
        with pytest.raises(RuntimeError, match="setup"):
            operation(d)


def test_no_setup_can_plan_and_run_directly(tmp_path, monkeypatch):
    d = definition(tmp_path, monkeypatch)
    prepare(d)
    lifecycle.create_plan(d)
    lifecycle.run(d)
    assert lifecycle.setup(d) is None
    assert not (metadata_path(d) / "setup").exists()


@pytest.mark.parametrize("job, reason", [
    ({"id": "launch", "command": ["/no/such/setup-program"]}, "No such file"),
    ({"id": "slow", "command": [sys.executable, "-c", "import time; time.sleep(10)"], "timeout_s": .05}, "timed out"),
])
def test_launch_and_timeout_are_setup_failure(tmp_path, monkeypatch, job, reason):
    d = definition(tmp_path, monkeypatch, [job]); prepare(d)
    with pytest.raises(RuntimeError, match=reason): lifecycle.setup(d)
    assert load_state(d)["setup_status"] == "FAILED"
    root = Path(load_state(d)["last_setup_dir"])
    record, = root.glob("jobs/*/execution.json")
    assert read(record)["status"] == "FAILED"
    with pytest.raises(RuntimeError, match="setup"): lifecycle.create_plan(d)


def test_interrupt_leaves_setup_blocked(tmp_path, monkeypatch):
    d = definition(tmp_path, monkeypatch, [{"id": "a", "command": [sys.executable, "-c", "pass"]}])
    prepare(d)
    from mockingbird.adapter_utils import setup as boundary
    def interrupt(*args, **kwargs): raise KeyboardInterrupt()
    monkeypatch.setattr(boundary, "run_process", interrupt)
    with pytest.raises(KeyboardInterrupt): lifecycle.setup(d)
    root = Path(load_state(d)["last_setup_dir"])
    assert read(root / "setup.json")["status"] == "INTERRUPTED"
    record, = root.glob("jobs/*/execution.json")
    assert read(record)["status"] == "INTERRUPTED"
    with pytest.raises(RuntimeError, match="setup"): lifecycle.create_plan(d)


def test_yaml_is_frozen_but_script_edits_are_not(tmp_path, monkeypatch):
    d = definition(tmp_path, monkeypatch, [{"id": "a", "command": [sys.executable, "-c", "raise SystemExit(4)"]}])
    prepare(d)
    data = yaml.safe_load(Path(d['_definition_path']).read_text())
    data['setup']['jobs'][0]['command'][-1] = 'pass'
    Path(d['_definition_path']).write_text(yaml.safe_dump(data))
    edited = load_definition(d['_definition_path'])
    with pytest.raises(RuntimeError, match="exit=4"): lifecycle.setup(edited)
    prepare(edited)
    lifecycle.setup(edited)
    lifecycle.create_plan(edited)


def test_setup_defaults_and_literal_argument_rules():
    result = resolve_setup({"defaults": {"command": ["echo"], "timeout_s": 3},
                            "jobs": ["a", {"id": "b", "args": []}, {"id": "c", "args": ["hello"]}]})
    assert [j['payload']['args'] for j in result['jobs']] == [["a"], [], ["hello"]]


@pytest.mark.parametrize("config", [None, [], {"collect": {}}, {"jobs": {}},
    {"defaults": {"timeout_s": True}},
    {"defaults": {"command": ["echo"], "timeout_s": 1}, "jobs": ["a", "a"]},
    {"jobs": [{"id": "a", "command": ["echo"]}]},
    {"jobs": [{"id": "a", "command": ["echo"], "timeout_s": 1, "collect": {"mode": "no-check"}}]},
])
def test_invalid_contracts_rejected(config):
    with pytest.raises(ValueError): resolve_setup(config)


def test_doctor_probes_setup_without_executing(tmp_path, monkeypatch):
    d = definition(tmp_path, monkeypatch, [{"id": "a", "command": ["/missing/setup-command"]}])
    checks = run_doctor(d)
    assert doctor_failed(checks)
    assert any(c.component == 'setup' and c.status == 'FAIL' for c in checks)
    assert not metadata_path(d).exists()


def test_custom_adapter_hook_remains_required_and_fails_closed(tmp_path, monkeypatch):
    d = definition(tmp_path, monkeypatch)
    d["execution"] = {"adapter": "demo_linux", "config": {"tests": []}}
    prepare(d)
    with pytest.raises(RuntimeError, match="setup"): lifecycle.create_plan(d)
    lifecycle.setup(d)
    lifecycle.create_plan(d)
    class BrokenHook:
        def setup(self, context): raise RuntimeError("custom preparation failed")
    monkeypatch.setattr(lifecycle, "load_adapter", lambda _: BrokenHook())
    with pytest.raises(RuntimeError, match="custom preparation failed"): lifecycle.setup(d)
    assert load_state(d)["setup_status"] == "FAILED"
    assert not (metadata_path(d) / "plan.json").exists()


def test_setup_is_independent_of_run_capacity(tmp_path, monkeypatch):
    d = definition(tmp_path, monkeypatch, [{"id": "a", "command": [sys.executable, "-c", "pass"]}])
    d["scheduler"]["config"] = {"slots": 0}
    prepare(d)
    attempt = lifecycle.setup(d)
    assert read(attempt / "setup.json")["status"] == "SUCCEEDED"
