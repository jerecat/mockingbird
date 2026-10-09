"""Fault injection and boundary regressions from the maintenance review."""
import signal
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from mockingbird import context, lifecycle
from mockingbird.io import read_json, write_json
from mockingbird.models import Job, JobExecution, TestResult as Result
from mockingbird.scheduler import run_jobs
from mockingbird.testing import check_execution_adapter, check_capacity_provider


def definition(tmp_path, name="A"):
    return {
        'plan': name,
        '_definition_path': str(tmp_path / f'{name}.yaml'),
        '_invocation_dir': str(tmp_path),
        'scheduler': {'capacity_provider': 'fixed', 'poll_interval_s': 0.01},
        'execution': {'command': [sys.executable, '-c', 'pass'], 'args': [], 'timeout_s': 2, 'jobs': ['a', 'b']},
    }


def ready(d):
    context.prepare(d)
    lifecycle.setup(d)
    lifecycle.create_plan(d)


def test_wrong_definition_rejected_before_dispatch(tmp_path):
    ready(definition(tmp_path))
    with pytest.raises(RuntimeError, match="context not prepared"):
        lifecycle.run(definition(tmp_path, "B"))
    assert not list((tmp_path / "work/A/runs").iterdir())


def test_same_definition_edits_require_plan_without_prepare(tmp_path):
    d = definition(tmp_path)
    ready(d)
    d["execution"]["jobs"] = ["new"]
    assert [j.id for j in lifecycle.plan_jobs(d)] == ["a", "b"]
    lifecycle.create_plan(d)
    assert [j.id for j in lifecycle.plan_jobs(d)] == ["new"]


def test_collect_checks_run_definition_but_does_not_need_current_prepared_workspace(tmp_path):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    with pytest.raises(ValueError, match="different plan"):
        lifecycle.collect(definition(tmp_path, "B"), rd)
    write_json(tmp_path / "work/A/.reg/preparing.json", {"started_at": "interrupted"})
    assert lifecycle.collect(d, rd)[0]["collection_complete"]


def test_partial_prepare_invalidates_previous_plan_and_can_recover(tmp_path, monkeypatch):
    d = definition(tmp_path)
    d["sources"] = [{"name": n, "provider": "fake", "url": "fake"} for n in ["one", "two"]]
    class Provider:
        revision = "old"
        fail = False
        def materialize(self, source, destination):
            if self.fail and source["name"] == "two":
                raise OSError("source unavailable")
            write_json(destination / "version.json", self.revision)
            return {"resolved_revision": self.revision}
    provider = Provider()
    monkeypatch.setattr(context, "load_source_provider", lambda _: provider)
    ready(d)
    provider.revision = "new"
    provider.fail = True
    with pytest.raises(OSError):
        context.prepare(d)
    assert read_json(tmp_path / "work/A/sources/one/version.json") == "new"
    for operation in (lifecycle.setup, lifecycle.create_plan, lifecycle.run):
        with pytest.raises(RuntimeError, match="prepare is incomplete"):
            operation(d)
    provider.fail = False
    context.prepare(d)
    with pytest.raises(RuntimeError, match="stale"):
        lifecycle.run(d)
    lifecycle.setup(d)
    lifecycle.create_plan(d)
    lifecycle.run(d)


def test_prepare_metadata_failure_also_leaves_workspace_blocked(tmp_path, monkeypatch):
    d = definition(tmp_path)
    ready(d)
    def fail_state(path, value):
        if path.name == "state.json":
            raise OSError("state write failure")
        write_json(path, value)
    monkeypatch.setattr(context, "write_json", fail_state)
    with pytest.raises(OSError):
        context.prepare(d)
    with pytest.raises(RuntimeError, match="prepare is incomplete"):
        lifecycle.run(d)


def test_aggregate_execution_write_failure_does_not_lose_collectable_evidence(tmp_path, monkeypatch):
    d = definition(tmp_path)
    ready(d)
    def fail_snapshot(path, value):
        if path.name == "executions.json":
            raise OSError("snapshot unavailable")
        write_json(path, value)
    monkeypatch.setattr(lifecycle, "write_json", fail_snapshot)
    with pytest.raises(OSError, match="snapshot unavailable"):
        lifecycle.run(d)
    rd = Path(context.load_state(d)["last_run_dir"])
    assert len(list(rd.glob("jobs/*/execution.json"))) == 2
    result, _ = lifecycle.collect(d, rd)
    assert result["collection_complete"]
    assert result["summary"]["pass"] == 2


@pytest.mark.parametrize("broken_name", ["collection.json", "result.json"])
def test_derived_collection_write_failure_does_not_repeat_final_collectors(tmp_path, monkeypatch, broken_name):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    adapter = lifecycle.load_adapter("command")
    collect = Mock(wraps=adapter.collect)
    monkeypatch.setattr(adapter, "collect", collect)
    monkeypatch.setattr(lifecycle, "load_adapter", lambda _: adapter)
    def fail_snapshot(path, value):
        if path == rd / broken_name:
            raise OSError("snapshot unavailable")
        write_json(path, value)
    monkeypatch.setattr(lifecycle, "write_json", fail_snapshot)
    with pytest.raises(OSError):
        lifecycle.collect(d, rd)
    assert collect.call_count == 2
    monkeypatch.setattr(lifecycle, "write_json", write_json)
    result, _ = lifecycle.collect(d, rd)
    assert result["collection_complete"]
    assert collect.call_count == 2


def test_new_checkpoint_writes_scale_linearly(tmp_path, monkeypatch):
    d = definition(tmp_path)
    d["execution"]["jobs"] = [str(i) for i in range(12)]
    ready(d)
    spy = Mock(wraps=write_json)
    monkeypatch.setattr(lifecycle, "write_json", spy)
    _, rd, _ = lifecycle.run(d)
    lifecycle.collect(d, rd)
    paths = [call.args[0] for call in spy.call_args_list]
    assert paths.count(rd / "executions.json") == 1
    assert paths.count(rd / "collection.json") == 1
    assert len(list(rd.glob("jobs/*/execution.json"))) == 12
    assert len(list(rd.glob("jobs/*/collection.json"))) == 12


def test_legacy_schema_two_runs_remain_collectable(tmp_path):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    record = read_json(rd / "run.json")
    del record["checkpoint_storage"]
    write_json(rd / "run.json", record)
    result, _ = lifecycle.collect(d, rd)
    assert result["collection_complete"]
    assert lifecycle.collect(d, rd)[0]["jobs"] == result["jobs"]


@pytest.mark.parametrize("value", [True, False, "1", float("nan"), float("inf"), -1, 0])
def test_invalid_poll_rejected_before_side_effects(tmp_path, value):
    d = definition(tmp_path)
    d["scheduler"]["poll_interval_s"] = value
    with pytest.raises(ValueError, match="finite positive"):
        context.prepare(d)
    assert not (tmp_path / "work").exists()
    capacity, execute = Mock(), Mock()
    with pytest.raises(ValueError, match="finite positive"):
        run_jobs([Job("x")], execute, capacity, 1, value)
    capacity.available_slots.assert_not_called()
    execute.assert_not_called()


@pytest.mark.parametrize("value", [True, False, "1", 1.5, -1, float("nan"), float("inf")])
def test_invalid_capacity_rejected_by_runtime_and_conformance(value):
    capacity = Mock()
    capacity.probe.return_value = []
    capacity.available_slots.return_value = value
    execute = Mock()
    with pytest.raises(ValueError, match="non-negative int"):
        run_jobs([Job("x")], execute, capacity, 1, .01)
    execute.assert_not_called()
    assert check_capacity_provider(capacity)[0].status == "FAIL"


def test_adapter_receives_same_contract_in_runtime_and_conformance(tmp_path, monkeypatch):
    class Adapter:
        def probe(self, context): return []
        def setup(self, context): pass
        def plan(self, context): return [Job("custom")]
        def execute(self, context, job, execution): return JobExecution(job.id, "start", "end", 0)
        def collect(self, context, executions):
            assert executions[0].run_id
            return [Result(e.contract["id"], "PASS") for e in executions]
    adapter = Adapter()
    d = definition(tmp_path)
    monkeypatch.setattr(lifecycle, "load_adapter", lambda _: adapter)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    assert lifecycle.collect(d, rd)[0]["status"] == "PASS"
    assert all(c.status == "PASS" for c in check_execution_adapter(adapter, {}, tmp_path / "check"))


@pytest.mark.parametrize("value", [True, "1", float("nan"), float("inf")])
def test_prepared_context_cannot_bypass_runtime_poll_validation(tmp_path, value):
    d = definition(tmp_path)
    ready(d)
    path = tmp_path / "work/A/.reg/plan.json"
    data = read_json(path)
    data["context"]["scheduler"]["poll_interval_s"] = value
    # Simulate a context saved by an older, permissive implementation.
    import json
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="finite positive"):
        lifecycle.run(d)
    assert not list((tmp_path / "work/A/runs").iterdir())


@pytest.mark.parametrize("value", [True, "1", 1.5, -1])
def test_fixed_capacity_configuration_does_not_coerce(value):
    from mockingbird.capacity.fixed import Provider
    with pytest.raises(ValueError, match="non-negative int"):
        Provider({"slots": value})


@pytest.mark.parametrize("value", [True, "1", float("nan"), float("inf"), 0, -1])
def test_capacity_command_timeout_is_validated(value):
    from mockingbird.capacity.command import Provider
    with pytest.raises(ValueError, match="finite positive"):
        Provider({"command": ["unused"], "timeout_s": value})


@pytest.mark.parametrize("record_name", ["execution.json", "collection.json"])
def test_cross_run_job_checkpoints_are_rejected(tmp_path, record_name):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    lifecycle.collect(d, rd)
    path = next(rd.glob(f"jobs/*/{record_name}"))
    data = read_json(path)
    data["run_id"] = "another-run"
    write_json(path, data)
    with pytest.raises(ValueError, match="run"):
        lifecycle.collect(d, rd)


def test_termination_kills_surviving_group_even_after_parent_exit(monkeypatch):
    from mockingbird.adapter_utils import process
    child = Mock(pid=99999999)
    child.wait.return_value = 0
    kill = Mock()
    monkeypatch.setattr(process.os, "killpg", kill)
    process._terminate_process_group(child, 0)
    assert [c.args[1] for c in kill.call_args_list] == [signal.SIGTERM, signal.SIGKILL]


def test_interrupt_during_process_wait_cleans_up_before_propagating(tmp_path, monkeypatch):
    from mockingbird.adapter_utils import process
    from mockingbird.testing import make_execution_context
    child = Mock()
    child.wait.side_effect = KeyboardInterrupt
    monkeypatch.setattr(process.subprocess, "Popen", lambda *a, **kw: child)
    terminate = Mock()
    monkeypatch.setattr(process, "_terminate_process_group", terminate)
    with pytest.raises(KeyboardInterrupt):
        process.run_process(["unused"], make_execution_context(tmp_path))
    terminate.assert_called_once_with(child, 5.0)
