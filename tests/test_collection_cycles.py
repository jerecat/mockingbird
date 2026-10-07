import json
import sys
from pathlib import Path

import pytest
import yaml

from mockingbird import lifecycle
from mockingbird.context import load_definition, prepare
from mockingbird.io import collection_lock, read_json


def make_run(tmp_path, monkeypatch, jobs=None, collector=None):
    monkeypatch.chdir(tmp_path)
    cfg = {"defaults": {"command": [sys.executable, "-c", "pass"], "args": [], "timeout_s": 2},
           "jobs": jobs or ["a", "b"]}
    if collector:
        cfg["defaults"]["collect"] = {"command": [sys.executable, str(collector)], "timeout_s": 2}
    path = tmp_path / "regression.yaml"
    path.write_text(yaml.safe_dump({"execution": cfg, "sources": [], "scheduler": {
        "capacity_provider": "fixed", "max_parallel": 1, "poll_interval_s": 0.001, "config": {"slots": 1}}}))
    defn = load_definition(path)
    prepare(defn)
    lifecycle.setup(defn)
    lifecycle.create_plan(defn)
    return defn


def test_repeat_collect_only_retries_unresolved_and_does_not_execute(tmp_path, monkeypatch):
    script = tmp_path / "collect.py"
    script.write_text('''import os, pathlib, json, sys
job = os.environ['MB_JOB_ID']
assert job == sys.argv[1]
key = os.environ['MB_RUN_ID'] + '-' + job
p = pathlib.Path(key)
n = int(p.read_text()) + 1 if p.exists() else 1
p.write_text(str(n))
if job == 'b' and n == 1: print(json.dumps({'status':'PENDING'}))
elif job == 'c' and n == 1: sys.exit(7)
else: print(json.dumps({'status':'FAIL' if job == 'b' else 'PASS', 'artifacts':['opaque:' + key]}))
''')
    defn = make_run(tmp_path, monkeypatch, ["a", "b", "c"], script)
    _, run, _ = lifecycle.run(defn)
    evidence = (run / "executions.json").read_bytes()
    first, _ = lifecycle.collect(defn, run)
    assert first["status"] == "PENDING"
    assert first["summary"] == dict(total=3, **{"pass": 1}, fail=0, error=0, skip=0, pending=1, uncollected=0, collection_error=1)
    second, _ = lifecycle.collect(defn, run)
    assert second["status"] == "FAIL" and second["collection_complete"]
    assert second["tests"][0] == first["tests"][0]
    assert [second["collection"][j]["attempts"] for j in ["a", "b", "c"]] == [1, 2, 2]
    third, _ = lifecycle.collect(defn, run)
    assert third["collection"] == second["collection"]
    assert (run / "executions.json").read_bytes() == evidence
    _, other_run, _ = lifecycle.run(defn)
    other, _ = lifecycle.collect(defn, other_run)
    assert other["status"] == "PENDING"  # Same Job IDs, fresh run identity.
    assert other["tests"][0]["artifacts"] != first["tests"][0]["artifacts"]
    assert read_json(run / "run.json")["status"] == "EXECUTED"


def test_completed_checkpoint_survives_interrupted_collect(tmp_path, monkeypatch):
    defn = make_run(tmp_path, monkeypatch)
    _, run, _ = lifecycle.run(defn)
    adapter = lifecycle.load_adapter("command")
    original = adapter.collect
    calls = []
    def interrupted(context, executions):
        calls.append(executions[0].job_id)
        if executions[0].job_id == "b":
            raise KeyboardInterrupt()
        return original(context, executions)
    monkeypatch.setattr(adapter, "collect", interrupted)
    monkeypatch.setattr(lifecycle, "load_adapter", lambda _: adapter)
    with pytest.raises(KeyboardInterrupt):
        lifecycle.collect(defn, run)
    checkpoint = next(run.glob("jobs/*a_*/collection.json"))
    assert read_json(checkpoint)["entry"]["state"] == "COMPLETE"
    monkeypatch.setattr(adapter, "collect", original)
    result, _ = lifecycle.collect(defn, run)
    assert result["status"] == "PASS"
    assert result["collection"]["a"]["attempts"] == 1


def test_execution_evidence_is_saved_before_next_job_and_survives_error(tmp_path, monkeypatch):
    defn = make_run(tmp_path, monkeypatch, ["a", "b", "c"])
    adapter = lifecycle.load_adapter("command")
    original = adapter.execute
    def execute(context, job, execution):
        if job.id == "b":
            recorded = [read_json(p) for p in sorted(Path(execution.run_dir).glob("jobs/*/execution.json"))]
            assert [item["job_id"] for item in recorded] == ["a"]
            raise RuntimeError("executor broken")
        return original(context, job, execution)
    monkeypatch.setattr(adapter, "execute", execute)
    monkeypatch.setattr(lifecycle, "load_adapter", lambda _: adapter)
    with pytest.raises(RuntimeError, match="executor broken"):
        lifecycle.run(defn)
    run = next((tmp_path / "runs").iterdir())
    records = read_json(run / "executions.json")
    assert [r["job_id"] for r in records] == ["a", "b"]
    assert records[1]["observation"]["executor_error"]
    result, _ = lifecycle.collect(defn, run)
    assert result["status"] == "PENDING"
    assert result["summary"]["uncollected"] == 1


def test_concurrent_collect_is_rejected(tmp_path, monkeypatch):
    defn = make_run(tmp_path, monkeypatch)
    _, run, _ = lifecycle.run(defn)
    with collection_lock(run):
        with pytest.raises(RuntimeError, match="already running"):
            lifecycle.collect(defn, run)


def test_invalid_plan_does_not_leave_previous_plan_runnable(tmp_path, monkeypatch):
    defn = make_run(tmp_path, monkeypatch)
    adapter = lifecycle.load_adapter("command")
    monkeypatch.setattr(adapter, "plan", lambda _: (_ for _ in ()).throw(ValueError("bad plan")))
    monkeypatch.setattr(lifecycle, "load_adapter", lambda _: adapter)
    with pytest.raises(ValueError):
        lifecycle.create_plan(defn)
    with pytest.raises(RuntimeError, match="plan not created"):
        lifecycle.run(defn)


def test_cli_pending_exit_code_and_completed_noop(tmp_path, monkeypatch):
    from mockingbird.cli import main
    script = tmp_path / "collect.py"
    script.write_text('print(\'{"status":"PENDING"}\')')
    defn = make_run(tmp_path, monkeypatch, ["a"], script)
    _, run, _ = lifecycle.run(defn)
    monkeypatch.setattr(sys, "argv", ["mb", "collect", str(tmp_path / "regression.yaml"), "--run-dir", str(run)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    script.write_text('print(\'{"status":"PASS"}\')')
    main()
    script.write_text('raise RuntimeError("must not run")')
    main()
    assert read_json(run / "result.json")["collection"]["a"]["attempts"] == 2


def test_mismatched_custom_result_id_is_retryable_collection_error(tmp_path, monkeypatch):
    from mockingbird.models import TestResult
    defn = make_run(tmp_path, monkeypatch, ["a"])
    _, run, _ = lifecycle.run(defn)
    adapter = lifecycle.load_adapter("command")
    monkeypatch.setattr(adapter, "collect", lambda *_: [TestResult("wrong", "PASS")])
    monkeypatch.setattr(lifecycle, "load_adapter", lambda _: adapter)
    result, _ = lifecycle.collect(defn, run)
    assert result["tests"] == []
    assert result["summary"]["collection_error"] == 1
    monkeypatch.setattr(adapter, "collect", lambda *_: [TestResult("a", "FAIL")])
    result, _ = lifecycle.collect(defn, run)
    assert result["status"] == "FAIL"
    assert result["collection"]["a"]["attempts"] == 2
