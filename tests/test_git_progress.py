import json
import os
from pathlib import Path
import subprocess
import sys

from test_git_acquisition_failure import origin
from mockingbird.sources import git


def test_streamed_commands_inherit_stderr_and_do_not_capture_stdout(monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout=None)
    monkeypatch.setattr(git.subprocess, "run", run)
    assert git._run(["git", "clone"], stream=True) == ""
    assert calls[0]["stdout"] is sys.stderr
    assert calls[0]["stderr"] is None


def test_prepare_json_with_real_git_progress(tmp_path):
    source = origin(tmp_path)
    definition = tmp_path / "jobs.yaml"
    definition.write_text(json.dumps({
        "workspace": str(tmp_path / "work"),
        "sources": [{"name": "repo", "provider": "git", "url": str(source), "revision": "main"}],
        "execution": {"command": ["echo"], "timeout_s": 5, "jobs": ["a"]},
        "scheduler": {"capacity_provider": "fixed"},
    }))
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
               LC_ALL="C")
    result = subprocess.run(
        [sys.executable, "-m", "mockingbird.cli", "prepare", str(definition), "--json"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert isinstance(json.loads(result.stdout), dict)
    assert "Cloning into" in result.stderr
    assert "HEAD is now at" in result.stderr
    assert (tmp_path / "work/sources/repo/source.txt").read_text() == "original"
