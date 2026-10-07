from __future__ import annotations

import subprocess
from pathlib import Path

from mockingbird.sources.git import Provider


def _run(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        args, cwd=cwd, check=True, text=True, capture_output=True
    ).stdout.strip()


def test_git_provider_preserves_existing_worktree_and_reports_actual_revision(tmp_path):
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
    assert evidence["materialization"] == "created"
    assert _run(["git", "rev-parse", "HEAD"], destination) == first

    # Local edits, staged content, ignored output and untracked files all survive.
    (destination / "stale.tmp").write_text("stale")
    (destination / ".gitignore").write_text("output/\n")
    (destination / "output").mkdir()
    (destination / "output/log").write_text("keep")
    (destination / "value.txt").write_text("staged\n")
    _run(["git", "add", "value.txt"], destination)
    (destination / "value.txt").write_text("edited again\n")
    before = _run(["git", "status", "--porcelain", "--ignored"], destination)
    _run(["git", "checkout", "-b", "local-work"], destination)
    (origin / "value.txt").write_text("two\n")
    _run(["git", "add", "value.txt"], origin)
    _run(["git", "commit", "-m", "two"], origin)
    second = _run(["git", "rev-parse", "HEAD"], origin)

    evidence = provider.materialize(
        {"url": str(tmp_path / "unreachable"), "revision": second}, destination
    )
    assert evidence["resolved_revision"] == first
    assert evidence["materialization"] == "reused"
    assert evidence["provider_metadata"]["origin_url"] == str(origin)
    assert (destination / "stale.tmp").read_text() == "stale"
    assert (destination / "output/log").read_text() == "keep"
    assert (destination / "value.txt").read_text() == "edited again\n"
    assert _run(["git", "show", ":value.txt"], destination) == "staged"
    assert _run(["git", "status", "--porcelain", "--ignored"], destination) == before
    assert _run(["git", "branch", "--show-current"], destination) == "local-work"


def test_git_reuse_issues_only_local_read_commands(tmp_path, monkeypatch):
    from mockingbird.sources import git
    destination = tmp_path / "worktree"
    destination.mkdir()
    (destination / ".git").write_text("gitdir: elsewhere")
    calls = []
    def read_only(args, *, cwd=None, env=None):
        calls.append(args)
        return "actual" if args[1] == "rev-parse" else "local-origin"
    monkeypatch.setattr(git, "_run", read_only)
    evidence = git.Provider().materialize({"url": "unused", "revision": "unused"}, destination)
    assert evidence["resolved_revision"] == "actual"
    assert calls == [["git", "rev-parse", "HEAD"], ["git", "remote", "get-url", "origin"]]
