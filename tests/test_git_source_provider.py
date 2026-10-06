from __future__ import annotations

import subprocess
from pathlib import Path

from mockingbird.sources.git import Provider


def _run(args, cwd: Path):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def test_git_provider_materializes_exact_revision(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)

    (source / "value.txt").write_text("one\n")
    subprocess.run(["git", "add", "value.txt"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-m", "one"], cwd=source, check=True, capture_output=True)
    first = _run(["git", "rev-parse", "HEAD"], source)

    (source / "value.txt").write_text("two\n")
    subprocess.run(["git", "commit", "-am", "two"], cwd=source, check=True, capture_output=True)

    destination = tmp_path / "materialized"
    evidence = Provider().materialize(
        {"name": "dut", "url": str(source), "revision": first}, destination
    )

    assert evidence["resolved_revision"] == first
    assert _run(["git", "rev-parse", "HEAD"], destination) == first
    assert (destination / "value.txt").read_text() == "one\n"


def test_git_provider_resolves_remote_branch_name(tmp_path: Path):
    source = tmp_path / "source_branch"
    source.mkdir()
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    (source / "value.txt").write_text("main\n")
    subprocess.run(["git", "add", "value.txt"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-m", "main"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "release/r1"], cwd=source, check=True, capture_output=True)
    (source / "value.txt").write_text("release\n")
    subprocess.run(["git", "commit", "-am", "release"], cwd=source, check=True, capture_output=True)
    release = _run(["git", "rev-parse", "HEAD"], source)
    subprocess.run(["git", "checkout", "-"], cwd=source, check=True, capture_output=True)

    destination = tmp_path / "materialized_branch"
    evidence = Provider().materialize(
        {"name": "dut", "url": str(source), "revision": "release/r1"}, destination
    )
    assert evidence["resolved_revision"] == release
    assert (destination / "value.txt").read_text() == "release\n"
