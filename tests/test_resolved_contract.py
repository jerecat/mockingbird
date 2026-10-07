import copy
import math
import sys

import pytest

from mockingbird.adapters.command import Adapter
from mockingbird.models import CollectionAttempt
from mockingbird.testing import make_execution_context


def context(tmp_path, config):
    return {"invocation_dir": str(tmp_path), "paths": {"adapter_workdir": str(tmp_path / "work")},
            "execution": {"adapter": "command", "config": config}}


def test_defaults_resolve_full_contract_and_explicit_empty_and_replacement(tmp_path):
    config = {"defaults": {"command": ["first"], "args": ["default"], "timeout_s": 3,
                            "collect": {"command": ["collect"], "timeout_s": 4}},
              "jobs": ["a", {"id": "b", "command": ["other"], "args": [], "timeout_s": 8,
                              "collect": {"mode": "no-check"}}]}
    original = copy.deepcopy(config)
    jobs = Adapter().plan(context(tmp_path, config))
    assert config == original
    assert jobs[0].payload == {"command": ["first"], "args": ["default"], "timeout_s": 3.0,
                                "collect": {"command": ["collect"], "args": ["a"], "timeout_s": 4.0}}
    assert jobs[1].payload == {"command": ["other"], "args": [], "timeout_s": 8.0, "collect": {"mode": "no-check"}}
    config["defaults"]["command"][0] = "changed"
    assert jobs[0].payload["command"] == ["first"]


@pytest.mark.parametrize("override", [
    {"timeout_s": None}, {"timeout_s": True}, {"timeout_s": "3"},
    {"timeout_s": 0}, {"timeout_s": -1}, {"timeout_s": math.inf}, {"timeout_s": math.nan},
    {"args": None}, {"args": "bad"}, {"command": []}, {"command": [""]},
    {"timeuot_s": 3}, {"collect": {"mode": "exit-code"}},
    {"collect": {"command": ["collect"]}}, {"collect": {"mode": "no-check", "args": []}},
    {"collect": {"command": ["collect"], "timeout_s": 1, "typo": 0}},
])
def test_plan_rejects_invalid_resolved_contract(tmp_path, override):
    cfg = {"defaults": {"command": ["run"], "timeout_s": 3}, "jobs": [{"id": "a", **override}]}
    with pytest.raises(ValueError):
        Adapter().plan(context(tmp_path, cfg))


def test_duplicate_ids_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        Adapter().plan(context(tmp_path, {"command": ["run"], "timeout_s": 1, "jobs": ["a", "a"]}))


def test_execution_and_collection_use_frozen_contract_not_live_defaults(tmp_path):
    ctx = context(tmp_path, {"defaults": {"command": [sys.executable, "-c", "import sys;sys.exit(17)"],
                                         "args": [], "timeout_s": 1}, "jobs": ["a"]})
    adapter = Adapter()
    job = adapter.plan(ctx)[0]
    ctx["execution"]["config"] = {"command": ["must-not-run"]}
    record = adapter.execute(ctx, job, make_execution_context(tmp_path / "run"))
    assert record.observation["returncode"] == 17
    result = adapter.collect(ctx, [record])[0]
    assert result.status == "PASS" and result.artifacts == []


def test_launch_failure_is_execution_evidence_not_a_test_result(tmp_path):
    ctx = context(tmp_path, {"command": ["/does-not-exist-mockingbird"], "timeout_s": 1, "jobs": ["a"]})
    adapter = Adapter()
    record = adapter.execute(ctx, adapter.plan(ctx)[0], make_execution_context(tmp_path / "run"))
    assert "launch_error" in record.observation
    assert adapter.collect(ctx, [record])[0].status == "PASS"


@pytest.mark.parametrize("code, expected", [
    ('print(\'{"status":"PENDING"}\')', "PENDING"),
    ('print(\'{"status":"ERROR"}\')', "FINAL_ERROR"),
    ('print(\'{"id":"wrong", "status":"PASS"}\')', "ERROR"),
    ('print("bad json")', "ERROR"),
    ('import sys;sys.exit(9)', "ERROR"),
    ('import time;time.sleep(2)', "ERROR"),
])
def test_collection_pending_and_protocol_error_are_not_test_error(tmp_path, code, expected):
    ctx = context(tmp_path, {"command": [sys.executable, "-c", "pass"], "timeout_s": 1,
        "collect": {"command": [sys.executable, "-c", code], "timeout_s": 0.1}, "jobs": ["a"]})
    adapter = Adapter()
    record = adapter.execute(ctx, adapter.plan(ctx)[0], make_execution_context(tmp_path / "run"))
    outcome = adapter.collect(ctx, [record])[0]
    if expected == "FINAL_ERROR":
        assert not isinstance(outcome, CollectionAttempt)
        assert outcome.status == "ERROR"
    else:
        assert isinstance(outcome, CollectionAttempt)
        assert outcome.state == expected


def test_500_jobs_expand_independent_contracts(tmp_path):
    jobs = Adapter().plan(context(tmp_path, {"defaults": {"command": ["run"], "timeout_s": 1},
                                            "jobs": [f"job-{i}" for i in range(500)]}))
    assert len(jobs) == 500
    assert jobs[-1].payload == {"command": ["run"], "args": ["job-499"], "timeout_s": 1.0,
                                "collect": {"mode": "no-check"}}
    jobs[0].payload["command"].append("changed")
    assert jobs[1].payload["command"] == ["run"]
