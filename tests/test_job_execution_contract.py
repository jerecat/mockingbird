from __future__ import annotations

import json
from pathlib import Path

import pytest

from mockingbird import lifecycle
from mockingbird.context import load_definition, prepare


def _write(path: Path, job_id: str):
    path.write_text(
        f"""
name: job-contract
sources: []
execution:
  adapter: demo_linux
  config:
    tests:
      - id: {json.dumps(job_id)}
        command: [pwd]
scheduler:
  capacity_provider: fixed
  max_parallel: 1
  poll_interval_s: 0.01
  config: {{slots: 1}}
"""
    )


def test_core_allocates_isolated_per_job_execution_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    definition = tmp_path / "regression.yaml"
    _write(definition, "pcie/dma/write/seed-001")
    defn = load_definition(definition)
    prepare(defn)
    lifecycle.setup(defn)
    lifecycle.create_plan(defn)
    executions, run_dir, _ = lifecycle.run(defn)
    execution = executions[0]
    assert execution.paths["workdir"].startswith("jobs/")
    assert (run_dir / execution.paths["workdir"]).is_dir()
    assert (run_dir / execution.paths["artifact_dir"]).is_dir()
    assert (run_dir / execution.paths["logs_dir"]).is_dir()
    assert (run_dir / execution.paths["stdout"]).is_file()
    assert (run_dir / execution.paths["stderr"]).is_file()


def test_job_id_rejects_control_characters(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    definition = tmp_path / "regression.yaml"
    _write(definition, "bad\nid")
    defn = load_definition(definition)
    prepare(defn)
    lifecycle.setup(defn)
    with pytest.raises(ValueError, match="control"):
        lifecycle.create_plan(defn)


def test_job_id_rejects_leading_or_trailing_whitespace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    definition = tmp_path / "regression.yaml"
    _write(definition, " test ")
    defn = load_definition(definition)
    prepare(defn)
    lifecycle.setup(defn)
    with pytest.raises(ValueError, match="whitespace"):
        lifecycle.create_plan(defn)
