"""One user's plan names and their original working directories."""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path

from .io import file_lock, read_json, write_json


def plan_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise ValueError("plan must be 1-128 letters, digits, dots, underscores or hyphens, "
                         "starting with a letter or digit")
    return value


def entry_path(name):
    root = Path(os.environ.get("MB_STATE_DIR", str(Path.home() / ".local/state/mockingbird")))
    if not root.is_absolute():
        raise ValueError("MB_STATE_DIR must be an absolute path so plan lookup does not depend on cwd")
    return root / "plans" / (plan_name(name) + ".json")


def lookup(name):
    path = entry_path(name)
    if not path.exists():
        return None
    try:
        entry = read_json(path)
        if (entry["schema_version"] != 1 or entry["plan"] != name
                or not isinstance(entry["directory"], str)
                or not Path(entry["directory"]).is_absolute()
                or not isinstance(entry["definition_path"], str)
                or not Path(entry["definition_path"]).is_absolute()):
            raise ValueError("invalid fields")
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"invalid plan registration: {path}; restore or correct this file") from exc
    return entry


def resolve(name):
    entry = lookup(name)
    if entry is None:
        raise ValueError(
            f"plan {name!r} is not registered.\n"
            "For a new plan, run mb prepare <definition.yaml> from its project directory.\n"
            "To restore a registration, run mb prepare <definition.yaml> from its original project directory.")
    workspace = Path(entry["directory"]) / "work" / name
    if not (workspace / ".reg").is_dir():
        raise FileNotFoundError(
            f"registered plan {name!r} is unavailable at {workspace}.\n"
            f"Restore its saved files, or explicitly prepare it again using {entry['definition_path']}.\n"
            f"Registration: {entry_path(name)}")
    return Path(entry["directory"])


def definition_target(defn):
    entry = lookup(plan_name(defn.get("plan")))
    return dict(defn, _invocation_dir=entry["directory"]) if entry else dict(defn)


@contextmanager
def registration(defn):
    """Reserve a name before side effects; serialize registration for this name only."""
    name = plan_name(defn.get("plan"))
    path = entry_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path.with_suffix(".lock"), message=f"plan {name!r} registration is busy; retry shortly"):
        entry = lookup(name)
        candidate = Path(defn["_invocation_dir"]).resolve()
        directory = Path(entry["directory"]) if entry else candidate
        if not directory.is_dir():
            raise FileNotFoundError(
                f"registered project directory is missing: {directory}.\n"
                f"Restore it, or remove {path} before explicitly preparing a new location.")
        if candidate != directory and (candidate / "work" / name / ".reg/context.json").exists():
            raise ValueError(
                f"plan {name!r} is already registered at {directory / 'work' / name}; "
                f"another local environment exists at {candidate / 'work' / name}.\n"
                "Use the registered project directory to update this plan, or choose a different plan name.")
        if entry is None:
            write_json(path, {"schema_version": 1, "plan": name, "directory": str(directory),
                              "definition_path": str(Path(defn["_definition_path"]).resolve())})
        yield dict(defn, _invocation_dir=str(directory))
