from __future__ import annotations

from pathlib import Path

import regorch.sources.svn as svn_module


def test_svn_provider_contract_without_requiring_svn_binary(monkeypatch, tmp_path: Path):
    calls = []
    destination = tmp_path / "tb"

    def fake_run(args, *, cwd=None):
        calls.append(args)
        if args[:2] == ["svn", "checkout"]:
            (destination / ".svn").mkdir(parents=True)
            return ""
        if "revision" in args:
            return "18291"
        if "repos-root-url" in args:
            return "https://example.invalid/repos"
        return ""

    monkeypatch.setattr(svn_module, "_run", fake_run)
    evidence = svn_module.Provider().materialize(
        {
            "name": "testbench",
            "url": "https://example.invalid/repos/tb/trunk",
            "revision": "18291",
        },
        destination,
    )

    assert evidence["resolved_revision"] == "18291"
    assert calls[0] == [
        "svn",
        "checkout",
        "-r",
        "18291",
        "https://example.invalid/repos/tb/trunk",
        str(destination),
    ]
