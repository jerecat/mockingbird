from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from regorch.contracts import SourceProvider


def _run(args: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


class Provider(SourceProvider):
    def materialize(self, source: dict[str, Any], destination: Path) -> dict[str, Any]:
        url = str(source["url"])
        revision = str(source.get("revision", "HEAD"))
        destination.parent.mkdir(parents=True, exist_ok=True)

        if (destination / ".svn").exists():
            _run(["svn", "switch", url, str(destination)])
            _run(["svn", "update", "-r", revision, str(destination)])
        else:
            if destination.exists() and any(destination.iterdir()):
                raise RuntimeError(f"source destination is not empty: {destination}")
            _run(["svn", "checkout", "-r", revision, url, str(destination)])

        resolved = _run(["svn", "info", "--show-item", "revision", str(destination)])
        return {
            "resolved_revision": resolved,
            "provider_metadata": {
                "repository_root": _run(
                    ["svn", "info", "--show-item", "repos-root-url", str(destination)]
                )
            },
        }
