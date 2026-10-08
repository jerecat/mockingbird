from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from mockingbird.contracts import SourceProvider
from mockingbird.models import CheckResult


def _run(args: list[str], *, cwd: Path | None = None, env=None, stream=False) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        # Keep machine-readable CLI stdout clean, even for Git stdout.
        stdout=sys.stderr if stream else subprocess.PIPE,
        stderr=None if stream else subprocess.PIPE,
    )
    return "" if stream else completed.stdout.strip()


def _try_run(args: list[str], *, cwd: Path) -> str | None:
    try:
        return _run(args, cwd=cwd)
    except subprocess.CalledProcessError:
        return None


def _resolve_revision(destination: Path, revision: str) -> str:
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
    def probe(self, source: dict[str, Any]):
        component = f"source:{source.get('name', '?')}"
        if shutil.which("git") is None:
            return [CheckResult(component, "git", "FAIL", "git executable not found")]
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            version = _run(["git", "--version"], env=env)
            _run(["git", "ls-remote", str(source["url"])], env=env, cwd=source.get("_invocation_dir"))
        except Exception as exc:
            return [
                CheckResult(component, "git", "PASS", version if 'version' in locals() else "git found"),
                CheckResult(component, "repository", "FAIL", f"{type(exc).__name__}: {exc}"),
            ]
        return [
            CheckResult(component, "git", "PASS", version),
            CheckResult(component, "repository", "PASS", "repository reachable without interactive prompt"),
        ]

    def observe(self, source):
        observation = {"prepared_commit": source.get("resolved_revision"),
                       "current_commit": None, "dirty": None}
        destination = Path(source["path"])
        def inspect(*args):
            return subprocess.run(["git", *args], cwd=destination, check=True,
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=10).stdout.strip()
        try:
            observation["current_commit"] = inspect("rev-parse", "HEAD")
            observation["dirty"] = bool(inspect("status", "--porcelain", "--untracked-files=normal"))
        except Exception as exc:
            observation["error"] = f"{type(exc).__name__}: {exc}"
        return observation

    def materialize(self, source: dict[str, Any], destination: Path) -> dict[str, Any]:
        url = str(source["url"])
        revision = str(source.get("revision", "HEAD"))

        reused = (destination / ".git").exists()
        if not reused:
            if destination.exists() and any(destination.iterdir()):
                raise RuntimeError(f"source destination is not empty: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Publish only a complete checkout. A failed initial clone/checkout
            # must not become a reusable user tree on the next prepare.
            with tempfile.TemporaryDirectory(prefix=f".{destination.name}-clone-",
                                             dir=destination.parent) as staging:
                checkout = Path(staging) / "checkout"
                _run(["git", "clone", "--progress", "--no-checkout", url, str(checkout)],
                     cwd=source.get("_invocation_dir"), stream=True)
                resolved = _resolve_revision(checkout, revision)
                _run(["git", "checkout", "--progress", "--detach", resolved], cwd=checkout, stream=True)
                # Rename on the same filesystem. Never replace a nonempty tree.
                checkout.rename(destination)

        # Existing worktrees belong to the user, including local edits, index,
        # branches, ignored outputs and remote configuration. Inspect only.
        resolved = _run(["git", "rev-parse", "HEAD"], cwd=destination)

        return {
            "resolved_revision": resolved,
            "materialization": "reused" if reused else "created",
            "provider_metadata": {
                "head": resolved,
                "origin_url": _try_run(["git", "remote", "get-url", "origin"], cwd=destination),
            },
        }
