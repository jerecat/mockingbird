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


def _try_run(args: list[str], *, cwd: Path) -> str | None:
    try:
        return _run(args, cwd=cwd)
    except subprocess.CalledProcessError:
        return None


def _resolve_revision(destination: Path, revision: str) -> str:
    # A human-authored branch name should follow the freshly fetched remote,
    # not a stale local branch left in a reused checkout. Explicit SHAs/tags/
    # refs still fall back to normal Git revision resolution.
    candidates: list[str] = []
    if revision == "HEAD":
        candidates.append("refs/remotes/origin/HEAD^{commit}")
    else:
        candidates.append(f"refs/remotes/origin/{revision}^{{commit}}")
    candidates.append(f"{revision}^{{commit}}")

    for candidate in candidates:
        resolved = _try_run(["git", "rev-parse", "--verify", candidate], cwd=destination)
        if resolved:
            return resolved
    raise RuntimeError(f"cannot resolve git revision {revision!r} in {destination}")


class Provider(SourceProvider):
    def materialize(self, source: dict[str, Any], destination: Path) -> dict[str, Any]:
        url = str(source["url"])
        revision = str(source.get("revision", "HEAD"))

        if not (destination / ".git").exists():
            if destination.exists() and any(destination.iterdir()):
                raise RuntimeError(f"source destination is not empty: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            _run(["git", "clone", "--no-checkout", url, str(destination)])
        else:
            _run(["git", "remote", "set-url", "origin", url], cwd=destination)

        _run(["git", "fetch", "--all", "--tags", "--prune"], cwd=destination)
        resolved = _resolve_revision(destination, revision)
        _run(["git", "checkout", "--detach", "--force", resolved], cwd=destination)
        # The source tree is tool-owned. Remove stale tracked/untracked state so
        # the materialized tree corresponds to the resolved revision.
        _run(["git", "reset", "--hard", resolved], cwd=destination)
        _run(["git", "clean", "-ffdx"], cwd=destination)

        return {
            "resolved_revision": resolved,
            "provider_metadata": {
                "head": _run(["git", "rev-parse", "HEAD"], cwd=destination),
            },
        }
