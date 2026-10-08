"""Exercise the shipped reference scripts through the public CLI."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_mock_simv_user_journey(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    examples = tmp_path / "examples"
    examples.mkdir()
    for name in ("sample_run.py", "sample_collect.py", "sample_finish.py", "sample-collector.yaml"):
        shutil.copyfile(repo / "examples" / name, examples / name)
    env = dict(os.environ, PYTHONPATH=str(repo / "src"))

    def cli(cycle, *args, expected=0):
        proc = subprocess.run([sys.executable, "-m", "mockingbird.cli", cycle,
                               ("examples/sample-collector.yaml" if cycle in {"prepare", "doctor", "all"} else "sample-collector"), *args],
                              cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
        assert proc.returncode == expected, proc.stdout + proc.stderr

    for cycle in ("prepare", "setup", "plan", "run"):
        cli(cycle)
    rd = next((tmp_path / "work/sample-collector/runs").iterdir())
    root = tmp_path / "work/sample-results" / rd.name
    executions = (rd / "executions.json").read_bytes()
    assert all(e["observation"]["returncode"] == 0 for e in json.loads(executions))
    cli("collect", "--run-dir", str(rd), expected=2)
    first = json.loads((rd / "result.json").read_text())
    assert first["summary"] == {"total": 8, "pass": 2, "fail": 1, "error": 1,
                                "skip": 1, "pending": 1, "uncollected": 0, "collection_error": 2}
    assert first["status"] == "PENDING"
    for test in first["tests"]:
        if test["id"] == "test_no_check":
            assert test["artifacts"] == []
        else:
            assert {Path(a).name for a in test["artifacts"]} == {"result.txt", "tarmac.log", "wave.fsdb", "sim.log"}
            assert all(Path(a).is_file() for a in test["artifacts"])
    subprocess.run([sys.executable, str(examples / "sample_finish.py"), rd.name],
                   cwd=tmp_path, env=env, check=True, capture_output=True, timeout=10)
    cli("collect", "--run-dir", str(rd), expected=1)
    second = json.loads((rd / "result.json").read_text())
    assert second["collection_complete"] and second["status"] == "FAIL"
    assert second["summary"] == {"total": 8, "pass": 5, "fail": 1, "error": 1,
                                 "skip": 1, "pending": 0, "uncollected": 0, "collection_error": 0}
    for result in first["tests"]:
        assert result == next(t for t in second["tests"] if t["id"] == result["id"])
    cli("collect", "--run-dir", str(rd), expected=1)
    for job in root.iterdir():
        calls = job / "collector_calls.txt"
        if job.name == "test_no_check":
            assert not calls.exists()
        else:
            expected = 2 if job.name in {"test_pending", "test_collect_error", "test_bad_json"} else 1
            assert len(calls.read_text().splitlines()) == expected
    assert (rd / "executions.json").read_bytes() == executions
    cli("status", "--run-dir", str(rd))
