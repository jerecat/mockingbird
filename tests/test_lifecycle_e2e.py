from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from mockingbird import lifecycle
from mockingbird.context import load_definition, prepare
from mockingbird.selection import Selection


def _write_definition(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "name": "e2e",
                "workspace": "./work",
                "run_root": "./runs",
                "sources": [],
                "execution": {
                    "adapter": "demo_linux",
                    "config": {
                        "tests": [
                            {"id": "mkdir_ok", "command": ["mkdir", "-p", "scratch"]},
                            {"id": "list_ok", "command": ["ls", "-la"]},
                            {"id": "intentional_fail", "command": ["sh", "-c", "exit 7"]},
                        ]
                    },
                },
                "scheduler": {
                    "capacity_provider": "fixed",
                    "max_parallel": 2,
                    "poll_interval_s": 0.01,
                    "config": {"slots": 2},
                },
            }
        )
    )


def _prepare_to_plan(defn):
    prepare(defn)
    lifecycle.setup(defn)
    lifecycle.create_plan(defn)


def test_context_plan_run_result_evidence_chain_and_failed_rerun(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    definition_path = tmp_path / "regression.yaml"
    _write_definition(definition_path)
    defn = load_definition(definition_path)
    _prepare_to_plan(defn)

    executions, first_run, _ = lifecycle.run(defn)
    assert {item.job_id for item in executions} == {"mkdir_ok", "list_ok", "intentional_fail"}
    first_result, _ = lifecycle.collect(defn, first_run)

    assert first_result["status"] == "FAIL"
    assert first_result["summary"] == {
        "total": 3,
        "pass": 2,
        "fail": 1,
        "error": 0,
        "skip": 0,
    }
    assert first_result["duration_s"] is not None
    for test in first_result["tests"]:
        assert test["artifacts"]
        assert all(isinstance(item, str) for item in test["artifacts"])
    for name in ("context.json", "plan.json", "run.json", "executions.json", "result.json"):
        assert (first_run / name).exists()

    second_executions, second_run, meta = lifecycle.run(
        defn, Selection(failed_from=str(first_run))
    )
    assert [item.job_id for item in second_executions] == ["intentional_fail"]
    assert meta["failed_from_run_id"] == first_result["run_id"]
    assert len(meta["failed_from_sha256"]) == 64

    run_record = json.loads((second_run / "run.json").read_text())
    assert run_record["selection"]["selected_ids"] == ["intentional_fail"]
    assert run_record["selection"]["failed_from"] == str((first_run / "result.json").resolve())


def test_reprepare_invalidates_old_plan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    definition_path = tmp_path / "regression.yaml"
    _write_definition(definition_path)
    defn = load_definition(definition_path)
    _prepare_to_plan(defn)

    # A new prepare creates a new frozen context. The old plan must not run.
    prepare(defn)
    with pytest.raises(RuntimeError, match="stale"):
        lifecycle.preview(defn, Selection())
