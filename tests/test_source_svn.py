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
