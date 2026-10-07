from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .io import read_json, write_json
from .plugins import load_source_provider
from .scheduler import validate_max_parallel
from .validation import positive_seconds


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_definition(path: str | Path) -> dict[str, Any]:
    p = Path(path).resolve()
    data = yaml.safe_load(p.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError("definition root must be a mapping")
    data["_definition_path"] = str(p)
    data["_invocation_dir"] = str(Path.cwd().resolve())
    return data


def _from_invocation(defn: dict[str, Any], value: str) -> Path:
    p = Path(value)
    if not p.is_absolute():
        p = Path(defn["_invocation_dir"]) / p
    return p.resolve()


def workspace_path(defn: dict[str, Any]) -> Path:
    return _from_invocation(defn, defn.get("workspace", "./work"))


def run_root_path(defn: dict[str, Any]) -> Path:
    return _from_invocation(defn, defn.get("run_root", "./runs"))


def metadata_path(defn: dict[str, Any]) -> Path:
    return workspace_path(defn) / ".reg"


def _validate_sources(sources: list[dict[str, Any]]) -> None:
    names: set[str] = set()
    for source in sources:
        for key in ("name", "provider", "url"):
            if not source.get(key):
                raise ValueError(f"source is missing required field {key!r}: {source!r}")
        name = str(source["name"])
        if name in names:
            raise ValueError(f"duplicate source name: {name}")
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError(f"source name must be a single safe path component: {name!r}")
        names.add(name)


def _normalize_execution(execution: Any) -> dict[str, Any]:
    if not isinstance(execution, dict):
        raise ValueError("execution must be a mapping")

    if execution.get("adapter"):
        if set(execution) - {"adapter", "config"}:
            raise ValueError(
                "execution cannot define both adapter and top-level command; "
                "put adapter-specific values under execution.config"
            )
        return dict(execution)

    if not any(key in execution for key in ("command", "defaults", "jobs")):
        raise ValueError("execution requires either command or adapter")

    # Declarative command execution is the normal path. Internally it still
    # crosses the same execution boundary as an advanced Python adapter.
    return {
        "adapter": "command",
        "config": dict(execution),
    }


def validate_definition(defn: dict[str, Any]) -> None:
    sources = list(defn.get("sources", []))
    if not all(isinstance(item, dict) for item in sources):
        raise ValueError("sources must be a list of mappings")
    _validate_sources(sources)

    _normalize_execution(defn.get("execution"))

    scheduler = defn.get("scheduler")
    if not isinstance(scheduler, dict) or not scheduler.get("capacity_provider"):
        raise ValueError("scheduler.capacity_provider is required")
    validate_max_parallel(scheduler.get("max_parallel", 1))
    positive_seconds(scheduler.get("poll_interval_s", 1.0), "scheduler.poll_interval_s")


def provisional_context(defn: dict[str, Any]) -> dict[str, Any]:
    """Build a non-frozen context for connection probes only."""

    validate_definition(defn)
    workspace = workspace_path(defn)
    run_root = run_root_path(defn)
    scheduler = dict(defn["scheduler"])
    scheduler["max_parallel"] = int(scheduler.get("max_parallel", 1))
    scheduler["poll_interval_s"] = float(scheduler.get("poll_interval_s", 1.0))
    return {
        "schema_version": 1,
        "name": defn.get("name", "regression"),
        "doctor": True,
        "definition_path": defn["_definition_path"],
        "invocation_dir": defn["_invocation_dir"],
        "paths": {
            "workspace": str(workspace),
            "sources_root": str(workspace / "sources"),
            "adapter_workdir": str(workspace / "exec"),
            "run_root": str(run_root),
        },
        "sources": [dict(item) for item in defn.get("sources", [])],
        "execution": _normalize_execution(defn["execution"]),
        "scheduler": scheduler,
    }


def prepare(defn: dict[str, Any]) -> dict[str, Any]:
    validate_definition(defn)
    workspace = workspace_path(defn)
    run_root = run_root_path(defn)
    sources_root = workspace / "sources"
    adapter_workdir = workspace / "exec"
    metadata = workspace / ".reg"

    for path in (workspace, sources_root, adapter_workdir, metadata, run_root):
        path.mkdir(parents=True, exist_ok=True)

    # Fail closed before touching mutable sources. A failed prepare must never
    # leave the previous plan executable against partially updated sources.
    write_json(metadata / "preparing.json", {"started_at": _now()})

    sources = list(defn.get("sources", []))
    resolved_sources: list[dict[str, Any]] = []

    for source in sources:
        destination = sources_root / str(source["name"])
        provider = load_source_provider(str(source["provider"]))
        evidence = provider.materialize(source, destination)
        resolved_sources.append(
            {
                "name": source["name"],
                "provider": source["provider"],
                "url": source["url"],
                "requested_revision": source.get("revision", "HEAD"),
                "config": dict(source.get("config", {})),
                "path": str(destination.resolve()),
                **evidence,
            }
        )

    execution = _normalize_execution(defn["execution"])
    scheduler = dict(defn["scheduler"])
    scheduler["max_parallel"] = int(scheduler.get("max_parallel", 1))
    scheduler["poll_interval_s"] = float(scheduler.get("poll_interval_s", 1.0))

    context = {
        "schema_version": 1,
        "name": defn.get("name", "regression"),
        "prepared_at": _now(),
        "orchestrator": {"name": "mockingbird", "version": __version__},
        "definition_path": defn["_definition_path"],
        "invocation_dir": defn["_invocation_dir"],
        "paths": {
            "workspace": str(workspace),
            "sources_root": str(sources_root),
            "adapter_workdir": str(adapter_workdir),
            "run_root": str(run_root),
        },
        "sources": resolved_sources,
        "execution": execution,
        "scheduler": scheduler,
    }
    write_json(metadata / "context.json", context)
    write_json(metadata / "state.json", {"prepared_at": context["prepared_at"]})
    (metadata / "preparing.json").unlink()
    return context


def load_context(defn: dict[str, Any]) -> dict[str, Any]:
    if (metadata_path(defn) / "preparing.json").exists():
        raise RuntimeError("prepare is incomplete; run 'mockingbird prepare' again")
    path = metadata_path(defn) / "context.json"
    if not path.exists():
        raise RuntimeError("context not prepared; run 'mockingbird prepare' first")
    context = read_json(path)
    validate_definition_identity(defn, context)
    return context


def validate_definition_identity(defn: dict[str, Any], context: dict[str, Any]) -> None:
    if Path(context["definition_path"]).resolve() != Path(defn["_definition_path"]).resolve():
        raise RuntimeError("saved context belongs to a different definition; use its definition or prepare this one explicitly")


def update_state(defn: dict[str, Any], **values: Any) -> dict[str, Any]:
    path = metadata_path(defn) / "state.json"
    state = read_json(path) if path.exists() else {}
    state.update(values)
    write_json(path, state)
    return state


def load_state(defn: dict[str, Any]) -> dict[str, Any]:
    path = metadata_path(defn) / "state.json"
    return read_json(path) if path.exists() else {}
