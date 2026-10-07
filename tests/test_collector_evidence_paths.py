import os
from pathlib import Path
import sys

import pytest

from mockingbird import lifecycle
from mockingbird.io import read_json, write_json
from test_review_regressions import definition, ready

REPO = Path(__file__).resolve().parents[1]
COLLECTOR = REPO / "examples/log_location_collect.py"
RUNNER = REPO / "examples/log_location_run.py"


def setup_definition(tmp_path):
    d = definition(tmp_path)
    d["execution"].update(
        command=[sys.executable, str(RUNNER)],
        collect={"command": [sys.executable, str(COLLECTOR)], "args": [], "timeout_s": 5})
    ready(d)
    return d


def result_file(execution):
    log = Path(execution.observation["execution_context"]["stdout_path"])
    return Path(log.read_text().strip().removeprefix("RESULT_DIR=")) / "result.txt"


def test_collect_old_run_and_pending_retry_use_original_logs(tmp_path):
    d = setup_definition(tmp_path)
    first, old, _ = lifecycle.run(d)
    waiting = result_file(first[1])
    waiting.unlink()
    second, new, _ = lifecycle.run(d)
    for item in second:
        result_file(item).write_text("FAIL")
    # A different live collector config must not affect the historical run.
    d["execution"]["collect"]["command"] = ["missing-live-collector"]
    result, _ = lifecycle.collect(d, old)
    assert result["summary"]["pass"] == 1
    assert result["summary"]["pending"] == 1
    waiting.write_text("PASS")
    result, _ = lifecycle.collect(d, old)
    assert result["summary"]["pass"] == 2
    result, _ = lifecycle.collect(d, new)
    assert result["summary"]["fail"] == 2


@pytest.mark.parametrize("launch_fails", [False, True])
def test_environment_points_to_execution_not_collection_logs(tmp_path, monkeypatch, launch_fails):
    d = definition(tmp_path)
    d["execution"]["jobs"] = ["a/b"]
    if launch_fails:
        d["execution"]["command"] = [str(tmp_path / "missing")]
    inspector = tmp_path / "inspect.py"
    inspector.write_text(
        "import json,os,pathlib\n"
        "record=pathlib.Path(os.environ['MB_EXECUTION_JSON'])\n"
        "data=json.loads(record.read_text())\n"
        "assert data['job_id']==os.environ['MB_JOB_ID']\n"
        "assert data['run_id']==os.environ['MB_RUN_ID']\n"
        "for key,field in [('MB_STDOUT_PATH','stdout_path'),('MB_STDERR_PATH','stderr_path')]:\n"
        " p=pathlib.Path(os.environ[key]); assert p.is_absolute()\n"
        " assert str(p)==data['observation']['execution_context'][field]\n"
        " assert not p.name.startswith('collect-')\n"
        "print(json.dumps({'status':'PASS','artifacts':[str(record)]}))\n")
    d["execution"]["collect"] = {"command": [sys.executable, str(inspector)], "args": [], "timeout_s": 5}
    for key in ("MB_STDOUT_PATH", "MB_STDERR_PATH", "MB_EXECUTION_JSON"):
        monkeypatch.setenv(key, "/wrong/inherited/value")
    ready(d)
    executions, rd, _ = lifecycle.run(d)
    if launch_fails:
        assert "launch_error" in executions[0].observation
    result, _ = lifecycle.collect(d, rd)
    assert result["summary"]["pass"] == 1


def test_legacy_aggregate_run_without_job_record_still_supplies_log_paths(tmp_path):
    d = setup_definition(tmp_path)
    executions, rd, _ = lifecycle.run(d)
    record = read_json(rd / "run.json")
    del record["checkpoint_storage"]
    write_json(rd / "run.json", record)
    for item in executions:
        (Path(item.observation["execution_context"]["job_dir"]) / "execution.json").unlink()
    result, _ = lifecycle.collect(d, rd)
    assert result["summary"]["pass"] == 2


@pytest.mark.parametrize("log", ["", "RESULT_DIR=/one\nRESULT_DIR=/two\n", "RESULT_DIR=relative\n"])
def test_sample_rejects_missing_or_ambiguous_location(tmp_path, log):
    import runpy
    from unittest.mock import patch
    stdout = tmp_path / "stdout.log"
    stdout.write_text(log)
    with patch.dict(os.environ, MB_STDOUT_PATH=str(stdout)):
        collect = runpy.run_path(str(COLLECTOR))["collect"]
        assert collect()["status"] == "ERROR"
