"""Run the guided public CLI, including early exits and directory protection."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[1]


def cli(root, *args, answers=None):
    return subprocess.run([sys.executable, "-m", "mockingbird.cli", "tutorial", *map(str, args)],
                          cwd=root, env=dict(os.environ, PYTHONPATH=str(REPO / "src")),
                          input=answers, text=True, capture_output=True, timeout=20)


@pytest.mark.parametrize("automatic, advanced", [(True, False), (False, False), (True, True)])
def test_tutorial_complete_and_cleanup_is_only_guidance(tmp_path, automatic, advanced):
    target = tmp_path / "exercise with spaces"
    result = cli(tmp_path, "--directory", target, *(["--yes"] if automatic else []), *(["--advanced"] if advanced else []),
                 answers=None if automatic else "\n" * 14)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Tutorial complete." in result.stdout
    assert "expected 2" in result.stdout
    assert result.stdout.count("$ mb collect ") == 2
    assert "Collect once more" not in result.stdout
    if not advanced:
        assert "--pending-only" in result.stdout
        assert "test_collect_error" not in result.stdout
        assert "expected 1" not in result.stdout
    assert shlex.join(["rm", "-rf", "--", str(target)]) in result.stdout
    assert target.is_dir() and (target / "GUIDE.md").is_file()
    assert not (tmp_path / "work").exists() and not (tmp_path / "runs").exists()
    run, = (target / "work/sample-collector/runs").iterdir()
    summary = json.loads((run / "result.json").read_text())["summary"]
    expected = {"total": 8, "pass": 5, "fail": 1, "error": 1, "skip": 1,
                       "pending": 0, "uncollected": 0, "collection_error": 0}
    if not advanced:
        expected = {"total": 2, "pass": 2, "fail": 0, "error": 0, "skip": 0,
                    "pending": 0, "uncollected": 0, "collection_error": 0}
    assert summary == expected
    project = target / "work/sample-results" / run.name
    for job in project.iterdir():
        calls = job / "collector_calls.txt"
        if job.name == "test_no_check":
            assert not calls.exists()
        else:
            expected = 2 if job.name in {"test_pending", "test_collect_error", "test_bad_json"} else 1
            assert len(calls.read_text().splitlines()) == expected
        assert (job / "wave.fsdb").is_file()


@pytest.mark.parametrize("answers", ["q\n", ""])
def test_cancel_before_creation(tmp_path, answers):
    result = cli(tmp_path, answers=answers)
    assert result.returncode == 0 and "no files created" in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_quit_after_creation_keeps_manual_guide(tmp_path):
    result = cli(tmp_path, answers="\nq\n")
    assert result.returncode == 0 and "Tutorial stopped" in result.stdout
    target, = tmp_path.iterdir()
    assert target.name.startswith("mb-tutorial-")
    assert (target / "GUIDE.md").is_file()
    assert not (target / "work").exists()
    assert "rm -rf --" in result.stdout


def test_existing_directory_and_symlink_are_refused(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("user edits")
    link = tmp_path / "linked"
    link.symlink_to(target, target_is_directory=True)
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "missing", target_is_directory=True)
    for path in (target, link, dangling):
        result = cli(tmp_path, "--directory", path, "--yes")
        assert result.returncode == 1 and "Traceback" not in result.stderr
    assert sentinel.read_text() == "user edits"
    assert list(target.iterdir()) == [sentinel]
    assert not (tmp_path / "missing").exists()


def test_failed_step_stops_and_keeps_evidence(tmp_path, monkeypatch, capsys):
    from mockingbird import tutorial
    class FailedProcess:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def wait(self): return 9
    monkeypatch.setattr(tutorial.subprocess, "Popen", FailedProcess)
    target = tmp_path / "exercise"
    with pytest.raises(RuntimeError, match="tutorial step failed"):
        tutorial.run_tutorial(str(target), automatic=True)
    output = capsys.readouterr().out
    assert "Tutorial complete" not in output and "Tutorial stopped" in output
    assert (target / "GUIDE.md").exists()


def test_installed_without_examples_has_actionable_error(monkeypatch):
    from mockingbird import tutorial
    monkeypatch.setattr(tutorial, "__file__", "/not-a-clone/lib/mockingbird/tutorial.py")
    with pytest.raises(ValueError, match="clone.*install"):
        tutorial._examples()
