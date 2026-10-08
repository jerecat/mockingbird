"""Bounded ENOSPC injection: persistence, dispatch, and recovery contracts."""
import errno
from pathlib import Path

import pytest

from mockingbird import io, lifecycle
from mockingbird.context import load_state
from mockingbird.adapters.command import Adapter
from test_review_regressions import definition, ready


def no_space(path):
    return OSError(errno.ENOSPC, "No space left on device", str(path))


@pytest.mark.parametrize("boundary", ["fsync", "replace"])
def test_enospc_preserves_previous_json_snapshot(tmp_path, monkeypatch, boundary):
    path = tmp_path / "result.json"
    io.write_json(path, {"old": True})
    before = path.read_bytes()

    def fail(*args):
        raise no_space(path)

    with monkeypatch.context() as patch:
        patch.setattr(io.os, boundary, fail)
        with pytest.raises(OSError) as error:
            io.write_json(path, {"new": True})
        assert error.value.errno == errno.ENOSPC
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["result.json"]


def test_execution_checkpoint_enospc_stops_next_dispatch(tmp_path, monkeypatch):
    d = definition(tmp_path)
    ready(d)
    dispatched = []
    original_execute = Adapter.execute

    def execute(self, context, job, execution):
        dispatched.append(job.id)
        return original_execute(self, context, job, execution)

    def fail_checkpoint(path, value):
        if path.name == "execution.json":
            raise no_space(path)
        io.write_json(path, value)

    monkeypatch.setattr(Adapter, "execute", execute)
    monkeypatch.setattr(lifecycle, "write_json", fail_checkpoint)
    with pytest.raises(OSError) as error:
        lifecycle.run(d)
    assert error.value.errno == errno.ENOSPC
    assert dispatched == ["a"]
    rd = Path(load_state(d)["last_run_dir"])
    assert io.read_json(rd / "run.json")["status"] == "ERROR"
    assert not list(rd.glob("jobs/*/execution.json"))
    # The command ran, but its missing checkpoint cannot be reconstructed.
    monkeypatch.setattr(lifecycle, "write_json", io.write_json)
    result, _ = lifecycle.collect(d, rd)
    assert result["summary"]["uncollected"] == 2
    assert not result["collection_complete"]


def test_terminal_record_enospc_leaves_stale_running_state(tmp_path, monkeypatch):
    d = definition(tmp_path)
    ready(d)

    def fail_terminal_record(path, value):
        if path.name == "run.json" and value["status"] != "RUNNING":
            raise no_space(path)
        io.write_json(path, value)

    monkeypatch.setattr(lifecycle, "write_json", fail_terminal_record)
    with pytest.raises(OSError) as error:
        lifecycle.run(d)
    assert error.value.errno == errno.ENOSPC
    rd = Path(load_state(d)["last_run_dir"])
    assert len(list(rd.glob("jobs/*/execution.json"))) == 2
    assert io.read_json(rd / "run.json")["status"] == "RUNNING"
    monkeypatch.setattr(lifecycle, "write_json", io.write_json)
    # Characterize the current recovery limit; this is not an ideal requirement.
    with pytest.raises(RuntimeError, match="not collectable"):
        lifecycle.collect(d, rd)


def test_result_enospc_retry_reuses_saved_collection_checkpoints(tmp_path, monkeypatch):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    collected = []
    original_collect = Adapter.collect

    def collect(self, context, executions):
        collected.extend(e.job_id for e in executions)
        return original_collect(self, context, executions)

    def fail_result(path, value):
        if path == rd / "result.json":
            raise no_space(path)
        io.write_json(path, value)

    monkeypatch.setattr(Adapter, "collect", collect)
    monkeypatch.setattr(lifecycle, "write_json", fail_result)
    with pytest.raises(OSError) as error:
        lifecycle.collect(d, rd)
    assert error.value.errno == errno.ENOSPC
    assert collected == ["a", "b"]
    monkeypatch.setattr(lifecycle, "write_json", io.write_json)
    result, _ = lifecycle.collect(d, rd)
    assert result["collection_complete"]
    assert result["summary"]["pass"] == 2
    assert collected == ["a", "b"]
