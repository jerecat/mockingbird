"""A real SIGINT must leave a collectable partial run."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest
import yaml

from mockingbird import lifecycle
from mockingbird.context import load_definition, prepare


def read(path):
    return json.loads(path.read_text())


def test_sigint_drains_current_job_and_preserves_partial_collection(tmp_path):
    marker = tmp_path / "current-job-started"
    definition = tmp_path / "regression.yaml"
    definition.write_text(yaml.safe_dump({
        'plan': 'test',
        'execution': {
            'defaults': {'command': [sys.executable, '-c', 'pass'], 'args': [], 'timeout_s': 5},
            'jobs': [
                'first',
                {
                    'id': 'current',
                    'command': [
                        sys.executable,
                        '-c',
                        f'from pathlib import Path; import time; Path({str(marker)!r}).touch(); time.sleep(1)',
                    ],
                },
                'not-started',
            ],
        },
        'scheduler': {
            'capacity_provider': 'fixed',
            'max_parallel': 1,
            'poll_interval_s': 0.01,
            'config': {'slots': 1},
        },
    }))
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))

    def cli(*args):
        return subprocess.run([sys.executable, "-m", "mockingbird.cli", *args],
                              cwd=tmp_path, env=env, capture_output=True,
                              text=True, timeout=10)

    for cycle in ("prepare", "setup", "plan"):
        completed = cli(cycle, "test" if cycle == "setup" else str(definition))
        assert completed.returncode == 0, completed.stderr

    process = subprocess.Popen(
        [sys.executable, "-m", "mockingbird.cli", "run", "test"],
        cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "current Job did not start"
        process.send_signal(signal.SIGINT)
        _, stderr = process.communicate(timeout=10)
        assert process.returncode == 130
        assert "Interrupted." in stderr and "mb status" in stderr
        assert "Traceback" not in stderr
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)

    run = Path(read(tmp_path / "work/test/.reg/last_run.json")["run_dir"])
    assert read(run / "run.json")["status"] == "INTERRUPTED"
    evidence = (run / "executions.json").read_bytes()
    assert [e["job_id"] for e in json.loads(evidence)] == ["first", "current"]
    assert all(e["observation"]["returncode"] == 0 for e in json.loads(evidence))

    collected = cli("collect", "test", "--run-dir", str(run))
    assert collected.returncode == 2, collected.stderr
    result = read(run / "result.json")
    assert result["status"] == "PENDING"
    assert result["summary"]["total"] == 3
    assert result["summary"]["pass"] == 2
    assert result["summary"]["uncollected"] == 1
    assert "not-started" not in {t["id"] for t in result["tests"]}
    assert read(run / "run.json")["status"] == "INTERRUPTED"
    again = cli("collect", "test", "--run-dir", str(run))
    assert again.returncode == 2
    assert read(run / "result.json")["collection"] == result["collection"]
    assert (run / "executions.json").read_bytes() == evidence


def test_interrupt_before_first_dispatch_is_collectable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    definition = tmp_path / "regression.yaml"
    definition.write_text(yaml.safe_dump({
        'plan': 'test',
        'execution': {'command': [sys.executable, '-c', 'pass'], 'timeout_s': 1, 'jobs': ['never-started']},
        'scheduler': {'capacity_provider': 'fixed', 'max_parallel': 1, 'config': {'slots': 1}},
    }))
    defn = load_definition(definition)
    prepare(defn)
    lifecycle.setup(defn)
    lifecycle.create_plan(defn)

    class InterruptedCapacity:
        def available_slots(self):
            raise KeyboardInterrupt()

    monkeypatch.setattr(lifecycle, "load_capacity_provider", lambda *_: InterruptedCapacity())
    with pytest.raises(KeyboardInterrupt):
        lifecycle.run(defn)
    run = Path(read(tmp_path / "work/test/.reg/last_run.json")["run_dir"])
    assert read(run / "run.json")["status"] == "INTERRUPTED"
    assert read(run / "executions.json") == []
    result, _ = lifecycle.collect(defn, run)
    assert result["status"] == "PENDING"
    assert result["tests"] == []
    assert result["summary"]["uncollected"] == 1
