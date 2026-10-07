"""Acquire a manifest-managed tree through the user's repo executable."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mockingbird.command_fields import mapping
from mockingbird.contracts import SourceProvider
from mockingbird.models import CheckResult


def _manifest(source):
    config = mapping(source.get("config", {}), "repo.config", {"manifest"})
    value = config.get("manifest", "default.xml")
    if (not isinstance(value, str) or not value or "\0" in value
            or Path(value).is_absolute() or ".." in Path(value).parts):
        raise ValueError("repo.config.manifest must be a relative manifest filename without '..'")
    return value


def _run(args, *, cwd, stream=False):
    result = subprocess.run(
        args, cwd=cwd, check=True, text=True,
        stdout=sys.stderr if stream else subprocess.PIPE,
        stderr=None if stream else subprocess.PIPE,
    )
    return "" if stream else result.stdout.strip()


class Provider(SourceProvider):
    def probe(self, source):
        component = f"source:{source.get('name', '?')}"
        try:
            _manifest(source)
        except ValueError as exc:
            return [CheckResult(component, "config", "FAIL", str(exc))]
        checks = [
            CheckResult(component, executable, "PASS" if shutil.which(executable) else "FAIL",
                        shutil.which(executable) or f"{executable} executable not found")
            for executable in ("repo", "git")
        ]
        checks.append(CheckResult(component, "manifest", "WARN",
                                  "manifest and project access are checked during prepare"))
        return checks

    def materialize(self, source, destination):
        manifest = _manifest(source)
        reused = (destination / ".repo").is_dir()
        if not reused:
            if destination.exists() and any(destination.iterdir()):
                raise RuntimeError(f"source destination is not empty: {destination}")
            for executable in ("repo", "git"):
                if shutil.which(executable) is None:
                    raise RuntimeError(f"{executable} executable not found on PATH")
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Publish only a successful initial sync. Never reset an existing tree.
            with tempfile.TemporaryDirectory(prefix=f".{destination.name}-repo-",
                                             dir=destination.parent) as staging:
                checkout = Path(staging) / "checkout"
                checkout.mkdir()
                _run(["repo", "init", "-u", str(source["url"]),
                      "-b", str(source.get("revision", "HEAD")), "-m", manifest],
                     cwd=checkout, stream=True)
                _run(["repo", "sync", "-j", "1"], cwd=checkout, stream=True)
                evidence = self._evidence(checkout)
                checkout.rename(destination)
        else:
            evidence = self._evidence(destination)
        return {
            "resolved_revision": evidence,
            "materialization": "reused" if reused else "created",
            "provider_metadata": {"manifest_revision": evidence},
        }

    @staticmethod
    def _evidence(destination):
        # This identifies the manifest baseline, not project HEADs or local edits.
        return _run(["git", "rev-parse", "HEAD"], cwd=destination / ".repo" / "manifests")
