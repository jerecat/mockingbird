from __future__ import annotations

import subprocess
from pathlib import Path

from mockingbird.sources.git import Provider


def _run(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        args, cwd=cwd, check=True, text=True, capture_output=True
    ).stdout.strip()


def test_git_provider_resolves_revision_and_cleans_workspace(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    _run(["git", "init", "-b", "main"], origin)
    _run(["git", "config", "user.email", "test@example.com"], origin)
    _run(["git", "config", "user.name", "Test"], origin)
    (origin / "value.txt").write_text("one\n")
    _run(["git", "add", "value.txt"], origin)
    _run(["git", "commit", "-m", "one"], origin)
    first = _run(["git", "rev-parse", "HEAD"], origin)

    destination = tmp_path / "checkout"
    provider = Provider()
    evidence = provider.materialize(
        {"url": str(origin), "revision": "main"}, destination
    )

    assert evidence["resolved_revision"] == first
    assert _run(["git", "rev-parse", "HEAD"], destination) == first

    # A later materialization must remove stale files from the tool-owned tree.
    (destination / "stale.tmp").write_text("stale")
    (origin / "value.txt").write_text("two\n")
    _run(["git", "add", "value.txt"], origin)
    _run(["git", "commit", "-m", "two"], origin)
    second = _run(["git", "rev-parse", "HEAD"], origin)

    evidence = provider.materialize(
        {"url": str(origin), "revision": "main"}, destination
    )
    assert evidence["resolved_revision"] == second
    assert not (destination / "stale.tmp").exists()
    assert (destination / "value.txt").read_text() == "two\n"
