from __future__ import annotations

import json
from pathlib import Path

from mockingbird import lifecycle
from mockingbird.context import load_definition, prepare
from mockingbird.selection import Selection


def _write_definition(path: Path):
    path.write_text(
        """
name: e2e
workspace: ./work
run_root: ./runs
sources: []
execution:
  adapter: demo_linux
  config:
    tests:
      - id: passing
        command: ["sh", "-c", "exit 0"]
      - id: failing
        command: ["sh", "-c", "exit 5"]
      - id: another
        command: ["ls", "-la"]
scheduler:
  capacity_provider: fixed
  max_parallel: 2
  poll_interval_s: 0.01
  config:
    slots: 2
"""
    )


def test_context_plan_run_result_and_failed_rerun(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    definition_file = tmp_path / "regression.yaml"
    _write_definition(definition_file)
    defn = load_definition(definition_file)

    context = prepare(defn)
    lifecycle.setup(defn)
    plan = lifecycle.create_plan(defn)
    executions, first_run, _ = lifecycle.run(defn)
    result, _ = lifecycle.collect(defn, first_run)

    assert Path(context["paths"]["workspace"]) == tmp_path / "work"
    assert [item["id"] for item in plan["jobs"]] == ["passing", "failing", "another"]
    assert len(executions) == 3
    assert result["summary"] == {"total": 3, "pass": 2, "fail": 1, "error": 0, "skip": 0}

    for evidence in ("context.json", "plan.json", "run.json", "executions.json", "result.json"):
        assert (first_run / evidence).is_file()

    previous_result = first_run / "result.json"
    _, second_run, selection = lifecycle.run(
        defn, Selection(failed_from=str(previous_result))
    )
    second_result, _ = lifecycle.collect(defn, second_run)

    assert selection["selected_ids"] == ["failing"]
    assert selection["failed_from"] == str(previous_result.resolve())
    assert second_result["summary"] == {"total": 1, "pass": 0, "fail": 1, "error": 0, "skip": 0}
    run_record = json.loads((second_run / "run.json").read_text())
    assert run_record["selection"]["failed_from"] == str(previous_result.resolve())
