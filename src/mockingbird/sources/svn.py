from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from mockingbird.contracts import SourceProvider
from mockingbird.models import CheckResult


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
    def probe(self, source: dict[str, Any]):
        component = f"source:{source.get('name', '?')}"
        if shutil.which("svn") is None:
            return [CheckResult(component, "svn", "FAIL", "svn executable not found")]
        try:
            version = _run(["svn", "--version", "--quiet"])
            revision = str(source.get("revision", "HEAD"))
            _run([
                "svn", "info", "--non-interactive", "-r", revision, str(source["url"])
            ])
        except Exception as exc:
            return [
                CheckResult(component, "svn", "PASS", version if 'version' in locals() else "svn found"),
                CheckResult(component, "repository", "FAIL", f"{type(exc).__name__}: {exc}"),
            ]
        return [
            CheckResult(component, "svn", "PASS", version),
            CheckResult(component, "repository", "PASS", "repository/revision reachable non-interactively"),
        ]

    def materialize(self, source: dict[str, Any], destination: Path) -> dict[str, Any]:
        url = str(source["url"])
        revision = str(source.get("revision", "HEAD"))
        destination.parent.mkdir(parents=True, exist_ok=True)

        reused = (destination / ".svn").exists()
        if not reused:
            if destination.exists() and any(destination.iterdir()):
                raise RuntimeError(f"source destination is not empty: {destination}")
            _run(["svn", "checkout", "-r", revision, url, str(destination)])

        resolved = _run(["svn", "info", "--show-item", "revision", str(destination)])
        return {
            "resolved_revision": resolved,
            "materialization": "reused" if reused else "created",
            "provider_metadata": {
                "working_copy_url": _run(
                    ["svn", "info", "--show-item", "url", str(destination)]
                ),
                "repository_root": _run(
                    ["svn", "info", "--show-item", "repos-root-url", str(destination)]
                )
            },
        }
