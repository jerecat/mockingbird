from __future__ import annotations

from typing import Any, Callable

from .context import provisional_context, validate_definition
from .models import CheckResult
from .plugins import load_adapter, load_capacity_provider, load_source_provider


def _safe(component: str, name: str, fn: Callable[[], list[CheckResult]]) -> list[CheckResult]:
    try:
        results = fn()
        if not isinstance(results, list) or not all(isinstance(item, CheckResult) for item in results):
            raise TypeError("probe must return list[CheckResult]")
        return results
    except Exception as exc:
        return [
            CheckResult(
                component=component,
                name=name,
                status="FAIL",
                message=f"{type(exc).__name__}: {exc}",
            )
        ]


def run_doctor(defn: dict[str, Any]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    try:
        validate_definition(defn)
        context = provisional_context(defn)
    except Exception as exc:
        return [
            CheckResult(
                component="configuration",
                name="definition",
                status="FAIL",
                message=f"{type(exc).__name__}: {exc}",
            )
        ]

    checks.append(
        CheckResult(
            component="configuration",
            name="definition",
            status="PASS",
            message="definition is structurally valid",
        )
    )

    for source in defn.get("sources", []):
        component = f"source:{source['name']}"
        try:
            provider = load_source_provider(str(source["provider"]))
            checks.append(CheckResult(component, "plugin", "PASS", str(source["provider"])))
        except Exception as exc:
            checks.append(CheckResult(component, "plugin", "FAIL", f"{type(exc).__name__}: {exc}"))
            continue
        checks.extend(_safe(component, "probe", lambda p=provider, s=source: p.probe(s)))

    try:
        adapter = load_adapter(str(context["execution"]["adapter"]))
        checks.append(
            CheckResult("execution", "plugin", "PASS", str(context["execution"]["adapter"]))
        )
        checks.extend(_safe("execution", "probe", lambda: adapter.probe(context)))
    except Exception as exc:
        checks.append(CheckResult("execution", "plugin", "FAIL", f"{type(exc).__name__}: {exc}"))

    if context.get("setup", {}).get("jobs"):
        try:
            setup_context = dict(context)
            setup_context["execution"] = {"adapter": "command", "config": {"jobs": [
                {"id": job["id"], **job["payload"]} for job in context["setup"]["jobs"]]}}
            for check in _safe("setup", "probe", lambda: load_adapter("command").probe(setup_context)):
                checks.append(CheckResult("setup", check.name, check.status, check.message, check.details))
        except Exception as exc:
            checks.append(CheckResult("setup", "probe", "FAIL", str(exc)))

    scheduler = context["scheduler"]
    try:
        capacity = load_capacity_provider(
            str(scheduler["capacity_provider"]), dict(scheduler.get("config", {}))
        )
        checks.append(
            CheckResult("capacity", "plugin", "PASS", str(scheduler["capacity_provider"]))
        )
        checks.extend(_safe("capacity", "probe", capacity.probe))
    except Exception as exc:
        checks.append(CheckResult("capacity", "plugin", "FAIL", f"{type(exc).__name__}: {exc}"))

    return checks


def doctor_failed(checks: list[CheckResult]) -> bool:
    return any(item.status.upper() == "FAIL" for item in checks)

