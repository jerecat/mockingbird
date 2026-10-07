import subprocess
from pathlib import Path

import pytest

from mockingbird.plugins import load_source_provider
from mockingbird.sources import repo


def source(**extra):
    return {"url": "ssh://server/manifests.git", "revision": "main",
            "config": {"manifest": "soc.xml"}, **extra}


def test_initial_commands_and_reuse_preserve_edits(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(repo.shutil, "which", lambda name: "/bin/" + name)
    def run(args, *, cwd, stream=False):
        calls.append((args, stream))
        if args[:2] == ["repo", "init"]:
            (cwd / ".repo/manifests").mkdir(parents=True)
        if args[:2] == ["repo", "sync"]:
            (cwd / "project").mkdir()
            (cwd / "project/file").write_text("original")
        return "manifest-sha"
    monkeypatch.setattr(repo, "_run", run)
    provider = load_source_provider("repo")
    destination = tmp_path / "tree"
    result = provider.materialize(source(), destination)
    assert result["resolved_revision"] == "manifest-sha"
    assert result["materialization"] == "created"
    assert calls[:2] == [
        (["repo", "init", "-u", "ssh://server/manifests.git", "-b", "main", "-m", "soc.xml"], True),
        (["repo", "sync", "-j", "1"], True),
    ]
    (destination / "project/file").write_text("user edit")
    calls.clear()
    result = provider.materialize(source(url="unused"), destination)
    assert result["materialization"] == "reused"
    assert calls == [(["git", "rev-parse", "HEAD"], False)]
    assert (destination / "project/file").read_text() == "user edit"


@pytest.mark.parametrize("stage", ["init", "sync"])
def test_failed_acquisition_not_reused(tmp_path, monkeypatch, stage):
    monkeypatch.setattr(repo.shutil, "which", lambda name: "/bin/" + name)
    calls = []
    def fail(args, *, cwd, stream=False):
        calls.append(args[1])
        (cwd / ".repo").mkdir(exist_ok=True)
        if args[1] == stage:
            raise subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(repo, "_run", fail)
    destination = tmp_path / "tree"
    for _ in range(2):
        with pytest.raises(subprocess.CalledProcessError):
            repo.Provider().materialize(source(), destination)
        assert not destination.exists()
        assert not list(tmp_path.glob(".tree-repo-*"))
    assert calls.count("init") == 2


@pytest.mark.parametrize("config", [{"manifest": None}, {"manifest": "../x.xml"},
                                    {"manifest": "/x.xml"}, {"manfiest": "x"}, []])
def test_invalid_config_has_no_side_effects(tmp_path, config):
    with pytest.raises(ValueError):
        repo.Provider().materialize(source(config=config), tmp_path / "tree")
    assert not list(tmp_path.iterdir())


def test_nonempty_destination_is_preserved(tmp_path):
    (tmp_path / "keep").write_text("user")
    with pytest.raises(RuntimeError, match="not empty"):
        repo.Provider().materialize(source(), tmp_path)
    assert (tmp_path / "keep").read_text() == "user"


def test_missing_executable_and_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(repo.shutil, "which", lambda name: None)
    checks = repo.Provider().probe(source())
    assert any(check.status == "FAIL" for check in checks)
    with pytest.raises(RuntimeError, match="repo executable not found"):
        repo.Provider().materialize(source(), tmp_path / "tree")
    assert not list(tmp_path.iterdir())


def test_destination_created_during_sync_is_not_replaced(tmp_path, monkeypatch):
    destination = tmp_path / "tree"
    monkeypatch.setattr(repo.shutil, "which", lambda name: "/bin/" + name)
    def run(args, *, cwd, stream=False):
        if args[:2] == ["repo", "sync"]:
            destination.mkdir()
            (destination / "keep").write_text("user")
        return "sha"
    monkeypatch.setattr(repo, "_run", run)
    with pytest.raises(OSError):
        repo.Provider().materialize(source(), destination)
    assert (destination / "keep").read_text() == "user"
