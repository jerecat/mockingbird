"""Progress is a saved observation, never a claim of external liveness."""
import json
from pathlib import Path
import sys
import threading

import pytest
import yaml

from mockingbird import lifecycle
from mockingbird.cli import _progress, _status
from mockingbird.context import load_definition, prepare
from mockingbird.io import read_json, write_json
from mockingbird.models import CollectionAttempt, Job, JobExecution, TestResult as Result
from mockingbird.scheduler import run_jobs
from mockingbird.status import snapshot


def prepared(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "jobs.yaml"
    path.write_text(yaml.safe_dump({
        'plan': 'test',
        'execution': {'command': [sys.executable, '-c', 'pass'], 'args': [], 'timeout_s': 2, 'jobs': ['a', 'b']},
        'scheduler': {'capacity_provider': 'fixed', 'poll_interval_s': 0.001},
    }))
    defn = load_definition(path)
    prepare(defn)
    lifecycle.setup(defn)
    lifecycle.create_plan(defn)
    return defn


def test_capacity_wait_emitted_once_and_execution_order_preserved():
    events = []
    class Capacity:
        values = iter([0, 0, 1, 1])
        def available_slots(self): return next(self.values)
    run_jobs([Job("a"), Job("b")], lambda j: JobExecution(j.id, "", "", 0),
             Capacity(), 1, .001, on_progress=lambda j, s: events.append((j.id, s)))
    assert events == [("a", "WAITING_CAPACITY"), ("a", "EXECUTING"), ("b", "EXECUTING")]


def test_status_available_during_run_before_any_collection(tmp_path, monkeypatch, capsys):
    defn = prepared(tmp_path, monkeypatch)
    adapter = lifecycle.load_adapter("command")
    original = adapter.execute
    entered, release = threading.Event(), threading.Event()
    def execute(context, job, execution):
        if job.id == "b":
            entered.set()
            assert release.wait(5)
        return original(context, job, execution)
    monkeypatch.setattr(adapter, "execute", execute)
    monkeypatch.setattr(lifecycle, "load_adapter", lambda _: adapter)
    errors = []
    def run():
        try: lifecycle.run(defn, on_progress=_progress)
        except BaseException as exc: errors.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(5)
        live = snapshot(defn)
        assert live["execution_status"] == "RUNNING"
        assert live["recorded"] == 1 and live["final"] == 0
        assert live["jobs"][1]["execution"] == "EXECUTING"
        _status(defn, None)
        output = capsys.readouterr().out
        assert "[2/2] b: executing" in output
        assert "NOT_STARTED" in output
        assert "liveness is not checked" in output
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not errors
    assert snapshot(defn)["execution_status"] == "EXECUTED"
    assert snapshot(defn)["recorded"] == 2


def test_status_reads_partial_checkpoints_not_stale_result(tmp_path, monkeypatch, capsys):
    defn = prepared(tmp_path, monkeypatch)
    _, rd, _ = lifecycle.run(defn)
    adapter = lifecycle.load_adapter("command")
    def collect(context, executions):
        if executions[0].job_id == "b": raise KeyboardInterrupt()
        return [CollectionAttempt("a", "PENDING", reason="simulation running")]
    monkeypatch.setattr(adapter, "collect", collect)
    monkeypatch.setattr(lifecycle, "load_adapter", lambda _: adapter)
    with pytest.raises(KeyboardInterrupt): lifecycle.collect(defn, rd)
    write_json(rd / "result.json", {"status": "PASS", "stale": True})
    before = (rd / "collection_progress.json").read_bytes()
    state = snapshot(defn)
    assert state["collection_sweep"]["state"] == "STOPPED"
    assert state["collection_counts"] == {"COMPLETE": 0, "PENDING": 1, "ERROR": 0, "UNCOLLECTED": 1}
    _status(defn, None, details=True)
    output = capsys.readouterr().out
    assert "Last collector report" in output and "simulation running" in output
    assert (rd / "collection_progress.json").read_bytes() == before


def test_status_selects_new_run_not_last_collected_run(tmp_path, monkeypatch, capsys):
    defn = prepared(tmp_path, monkeypatch)
    _, old, _ = lifecycle.run(defn)
    lifecycle.collect(defn, old)
    _, new, _ = lifecycle.run(defn)
    _status(defn, None, as_json=True)
    state = json.loads(capsys.readouterr().out)
    assert state["run_id"] == new.name and state["final"] == 0
    assert snapshot(defn, old)["final"] == 2


def test_legacy_and_stale_running_status_are_readable(tmp_path, monkeypatch):
    defn = prepared(tmp_path, monkeypatch)
    _, rd, _ = lifecycle.run(defn)
    record = read_json(rd / "run.json")
    del record["checkpoint_storage"]
    write_json(rd / "run.json", record)
    lifecycle.collect(defn, rd)
    assert snapshot(defn, rd)["final"] == 2
    record.update(status="RUNNING", finished_at=None)
    write_json(rd / "run.json", record)
    state = snapshot(defn, rd)
    assert state["execution_status"] == "RUNNING"
    assert state["last_execution_update"]


def test_display_separates_final_error_from_collection_error(tmp_path, monkeypatch, capsys):
    defn = prepared(tmp_path, monkeypatch)
    _, rd, _ = lifecycle.run(defn)
    adapter = lifecycle.load_adapter("command")
    def collect(context, executions):
        job_id = executions[0].job_id
        return [Result(job_id, "ERROR") if job_id == "a"
                else CollectionAttempt(job_id, "ERROR", reason="service unavailable")]
    monkeypatch.setattr(adapter, "collect", collect)
    monkeypatch.setattr(lifecycle, "load_adapter", lambda _: adapter)
    lifecycle.collect(defn, rd)
    _status(defn, str(rd))
    output = capsys.readouterr().out
    rows = [line.split() for line in output.splitlines() if line.startswith(("a ", "b "))]
    assert rows == [["a", "RECORDED", "COMPLETE", "ERROR"],
                    ["b", "RECORDED", "COLLECTION_ERROR", "-"]]
