from __future__ import annotations

from mockingbird.sources import svn


def test_svn_provider_contract_is_isolated_behind_provider(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, *, cwd=None):
        calls.append(list(args))
        if "revision" in args:
            return "18291"
        if "repos-root-url" in args:
            return "https://example.invalid/repos"
        return ""

    monkeypatch.setattr(svn, "_run", fake_run)
    destination = tmp_path / "tb"

    evidence = svn.Provider().materialize(
        {
            "url": "https://example.invalid/repos/tb/trunk",
            "revision": "18291",
        },
        destination,
    )

    assert evidence["resolved_revision"] == "18291"
    assert calls[0][:3] == ["svn", "checkout", "-r"]
    assert evidence["materialization"] == "created"


def test_svn_reuses_edited_working_copy_without_update_or_switch(tmp_path, monkeypatch):
    destination = tmp_path / "tb"
    (destination / ".svn").mkdir(parents=True)
    (destination / "source.sv").write_text("local edits")
    (destination / "untracked.log").write_text("user output")
    calls = []
    values = {"revision": "42", "url": "file:///local/tb", "repos-root-url": "file:///local"}
    def read_only(args, *, cwd=None):
        calls.append(args)
        assert args[:3] == ["svn", "info", "--show-item"]
        return values[args[3]]
    monkeypatch.setattr(svn, "_run", read_only)
    evidence = svn.Provider().materialize(
        {"url": "https://unreachable.invalid/other", "revision": "999"}, destination)
    assert evidence["resolved_revision"] == "42"
    assert evidence["materialization"] == "reused"
    assert evidence["provider_metadata"]["working_copy_url"] == "file:///local/tb"
    assert (destination / "source.sv").read_text() == "local edits"
    assert (destination / "untracked.log").read_text() == "user output"
    assert len(calls) == 3
