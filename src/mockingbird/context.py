from __future__ import annotations

import copy
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .errors import PrerequisiteError
from .io import file_lock, read_json, write_json
from .plugins import load_source_provider
from .setup_contract import resolve_setup, setup_required
from .scheduler import validate_max_parallel
from .validation import positive_seconds
from . import registry
from .registry import plan_name


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_definition(path: str | Path) -> dict[str, Any]:
    p = Path(path).resolve()
    data = yaml.safe_load(p.read_text())
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("definition root must be a mapping")
    _validate_definition_keys(data)
    data["_definition_path"] = str(p)
    data["_invocation_dir"] = str(Path.cwd().resolve())
    return data


_DEFINITION_KEYS = {"plan", "meta", "sources", "setup", "execution", "scheduler"}


def _validate_definition_keys(defn, *, internal=False):
    removed = set(defn) & {"name", "workspace", "run_root"}
    if removed:
        raise ValueError("obsolete definition field(s): " + ", ".join(sorted(removed)) +
                         "; use 'plan: <name>'; MB stores this plan under ./work/<name>/ "
                         "and its runs under ./work/<name>/runs/")
    allowed = _DEFINITION_KEYS | ({"_definition_path", "_invocation_dir"} if internal else set())
    unknown = set(defn) - allowed
    if unknown:
        hints = []
        for key in sorted(unknown, key=str):
            matches = get_close_matches(str(key), sorted(_DEFINITION_KEYS), n=1)
            hints.append(f"{key!r}" + (f" (did you mean {matches[0]!r}?)" if matches else ""))
        raise ValueError("unknown definition field(s): " + ", ".join(hints))


def _from_invocation(defn: dict[str, Any], value: str) -> Path:
    p = Path(value)
    if not p.is_absolute():
        p = Path(defn["_invocation_dir"]) / p
    return p.resolve()


def plan_target(name: str, directory: str | Path | None = None) -> dict[str, Any]:
    """Resolve a registered name; explicit directories also support legacy evidence."""
    name = plan_name(name)
    root = registry.resolve(name) if directory is None else Path(directory).resolve()
    return {"plan": name, "_invocation_dir": str(root)}


def workspace_path(defn: dict[str, Any]) -> Path:
    return _from_invocation(defn, "work") / plan_name(defn.get("plan"))


def run_root_path(defn: dict[str, Any]) -> Path:
    return workspace_path(defn) / "runs"


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
    _validate_definition_keys(defn, internal=True)
    plan_name(defn.get("plan"))
    if not isinstance(defn.get("meta", {}), dict):
        raise ValueError("meta must be a mapping")
    sources = list(defn.get("sources", []))
    if not all(isinstance(item, dict) for item in sources):
        raise ValueError("sources must be a list of mappings")
    _validate_sources(sources)

    _normalize_execution(defn.get("execution"))
    resolve_setup(defn.get("setup", {}))

    scheduler = defn.get("scheduler")
    if not isinstance(scheduler, dict) or not scheduler.get("capacity_provider"):
        raise ValueError("scheduler.capacity_provider is required")
    validate_max_parallel(scheduler.get("max_parallel", 1))
    positive_seconds(scheduler.get("poll_interval_s", 1.0), "scheduler.poll_interval_s")


def provisional_context(defn: dict[str, Any]) -> dict[str, Any]:
    """Build a non-frozen context for connection probes only."""

    validate_definition(defn)
    defn = registry.definition_target(defn)
    workspace = workspace_path(defn)
    run_root = run_root_path(defn)
    scheduler = dict(defn["scheduler"])
    scheduler["max_parallel"] = int(scheduler.get("max_parallel", 1))
    scheduler["poll_interval_s"] = float(scheduler.get("poll_interval_s", 1.0))
    return {
        "schema_version": 2,
        "plan": defn["plan"],
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
        "setup": resolve_setup(defn.get("setup", {})),
        "scheduler": scheduler,
    }


@contextmanager
def prepared_environment(defn, *, exclusive=False):
    metadata = metadata_path(defn)
    if not metadata.is_dir():
        load_context(defn)
    with file_lock(metadata / "environment.lock", shared=not exclusive,
                   message="plan environment is busy; finish active preparation/execution/collection first"):
        yield


def prepare(defn: dict[str, Any]) -> dict[str, Any]:
    validate_definition(defn)
    with registry.registration(defn) as target:
        metadata_path(target).mkdir(parents=True, exist_ok=True)
        with prepared_environment(target, exclusive=True):
            existing = metadata_path(target) / "context.json"
            if existing.exists():
                validate_definition_identity(target, read_json(existing))
            return _prepare(target)


def _prepare(defn: dict[str, Any]) -> dict[str, Any]:
    workspace = workspace_path(defn)
    run_root = run_root_path(defn)
    sources_root = workspace / "sources"
    adapter_workdir = workspace / "exec"
    execution = _normalize_execution(defn["execution"])
    metadata = workspace / ".reg"

    for path in (workspace, sources_root, metadata, run_root):
        path.mkdir(parents=True, exist_ok=True)

    # Custom adapters retain their prepared workspace contract. The command
    # adapter runs from invocation_dir and has no use for an exec directory.
    if execution["adapter"] != "command":
        adapter_workdir.mkdir(parents=True, exist_ok=True)

    # Fail closed before touching mutable sources. A failed prepare must never
    # leave the previous plan executable against partially updated sources.
    write_json(metadata / "preparing.json", {"started_at": _now()})

    sources = list(defn.get("sources", []))
    resolved_sources: list[dict[str, Any]] = []

    for source in sources:
        destination = sources_root / str(source["name"])
        provider = load_source_provider(str(source["provider"]))
        evidence = provider.materialize(dict(source, _invocation_dir=defn["_invocation_dir"]), destination)
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

    scheduler = dict(defn["scheduler"])
    scheduler["max_parallel"] = int(scheduler.get("max_parallel", 1))
    scheduler["poll_interval_s"] = float(scheduler.get("poll_interval_s", 1.0))

    context = {
        "schema_version": 2,
        "plan": defn["plan"],
        "prepared_at": _now(),
        "orchestrator": {"name": "mockingbird", "version": __version__, "python": sys.version},
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
        "setup": resolve_setup(defn.get("setup", {})),
        "scheduler": scheduler,
    }
    context["preparation_contract"] = preparation_contract(provisional_context(defn))
    write_json(metadata / "context.json", context)
    write_json(metadata / "state.json", {"prepared_at": context["prepared_at"]})
    entry = registry.lookup(defn["plan"])
    entry["definition_path"] = defn["_definition_path"]
    write_json(registry.entry_path(defn["plan"]), entry)
    (metadata / "preparing.json").unlink()
    return context


def _preparation_steps(defn):
    if "execution" not in defn:
        return ("prepare", "plan")
    context = {"execution": _normalize_execution(defn.get("execution")),
               "setup": resolve_setup(defn.get("setup", {}))}
    return ("prepare", "setup", "plan") if setup_required(context) else ("prepare", "plan")


def load_context(defn: dict[str, Any]) -> dict[str, Any]:
    if (metadata_path(defn) / "preparing.json").exists():
        raise PrerequisiteError("prepare is incomplete", *_preparation_steps(defn))
    path = metadata_path(defn) / "context.json"
    if not path.exists():
        raise PrerequisiteError("context not prepared", *_preparation_steps(defn))
    context = read_json(path)
    validate_definition_identity(defn, context)
    if Path(context["paths"]["workspace"]).resolve() != workspace_path(defn).resolve():
        raise PrerequisiteError("prepared environment was moved; prepare it in this directory", *_preparation_steps(defn))
    return context


def validate_definition_identity(defn: dict[str, Any], context: dict[str, Any]) -> None:
    if context.get("plan", context.get("name")) != defn["plan"]:
        raise ValueError("saved record belongs to a different plan")


def update_state(defn: dict[str, Any], **values: Any) -> dict[str, Any]:
    path = metadata_path(defn) / "state.json"
    state = read_json(path) if path.exists() else {}
    state.update(values)
    write_json(path, state)
    return state


def load_state(defn: dict[str, Any]) -> dict[str, Any]:
    path = metadata_path(defn) / "state.json"
    return read_json(path) if path.exists() else {}


def preparation_contract(context):
    """Fields whose changes require preparation rather than just a new plan."""
    sources = []
    for item in context.get("sources", []):
        if "requested_revision" in item:  # Compatibility with older saved contexts.
            source = {key: item[key] for key in ("name", "provider", "url")}
            source["revision"] = item["requested_revision"]
            source["config"] = item.get("config", {})
        else:
            source = dict(item)
            source.setdefault("revision", "HEAD")
            source.setdefault("config", {})
        sources.append(source)
    execution = context["execution"]
    return {
        "plan": context["plan"], "paths": context["paths"],
        "sources": sources, "setup": context.get("setup", {"jobs": []}),
        # Custom adapter setup may depend on its entire config.
        "execution": {"adapter": "command"} if execution["adapter"] == "command" else execution,
    }


def planning_context(defn, saved):
    """Overlay live execution intent without reacquiring or modifying sources."""
    current_defn = dict(defn, _invocation_dir=saved["invocation_dir"])
    current = provisional_context(current_defn)
    baseline = saved.get("preparation_contract", preparation_contract(saved))
    if preparation_contract(current) != baseline:
        raise PrerequisiteError(
            "preparation settings changed (sources, setup or adapter)",
            *_preparation_steps(defn))
    context = copy.deepcopy(saved)
    context["execution"] = current["execution"]
    context["scheduler"] = current["scheduler"]
    context["definition_path"] = defn["_definition_path"]
    return context
