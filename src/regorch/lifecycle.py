from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import (
    load_context,
    load_state,
    metadata_path,
    update_state,
)
from .io import read_json, write_json
from .models import Job, JobExecution, TestResult
from .plugins import load_adapter, load_capacity_provider
from .scheduler import run_jobs
from .selection import Selection, select_jobs


_CANONICAL_STATUSES = {"PASS", "FAIL", "ERROR", "SKIP"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp_id(name: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    return f"{stamp}_{safe}"


def _components(defn: dict[str, Any]):
    context = load_context(defn)
    adapter = load_adapter(str(context["execution"]["adapter"]))
    scheduler = context["scheduler"]
    capacity = load_capacity_provider(
        str(scheduler["capacity_provider"]), dict(scheduler.get("config", {}))
    )
    return context, adapter, capacity


def setup(defn: dict[str, Any]) -> None:
    context, adapter, _ = _components(defn)
    adapter.setup(context)
    update_state(defn, setup_at=_now(), setup_context_prepared_at=context["prepared_at"])


def create_plan(defn: dict[str, Any]) -> dict[str, Any]:
    state = load_state(defn)
    context = load_context(defn)
    if state.get("setup_context_prepared_at") != context["prepared_at"]:
        raise RuntimeError("setup is missing or stale; run 'reg setup' first")

    adapter = load_adapter(str(context["execution"]["adapter"]))
    jobs = adapter.plan(context)
    ids = [job.id for job in jobs]
    if len(ids) != len(set(ids)):
        raise ValueError("adapter returned duplicate job IDs")

    # The plan is persisted as evidence. Opaque payloads therefore still need
    # to be JSON-serializable, but core never interprets their contents.
    for job in jobs:
        json.dumps(job.to_dict())

    plan = {
        "schema_version": 1,
        "generated_at": _now(),
        "context_prepared_at": context["prepared_at"],
        "jobs": [job.to_dict() for job in jobs],
    }
    write_json(metadata_path(defn) / "plan.json", plan)
    update_state(
        defn,
        plan_at=plan["generated_at"],
        plan_context_prepared_at=context["prepared_at"],
    )
    return plan


def load_plan(defn: dict[str, Any]) -> dict[str, Any]:
    path = metadata_path(defn) / "plan.json"
    if not path.exists():
        raise RuntimeError("plan not created; run 'reg plan' first")
    plan = read_json(path)
    context = load_context(defn)
    if plan.get("context_prepared_at") != context.get("prepared_at"):
        raise RuntimeError("plan is stale for the current context; run 'reg setup' and 'reg plan'")
    return plan


def plan_jobs(defn: dict[str, Any]) -> list[Job]:
    plan = load_plan(defn)
    return [Job(**item) for item in plan["jobs"]]


def preview(defn: dict[str, Any], selection: Selection) -> tuple[dict, list[Job], dict]:
    context = load_context(defn)
    jobs = plan_jobs(defn)
    selected, selection_meta = select_jobs(jobs, selection)
    return context, selected, selection_meta


def run(
    defn: dict[str, Any], selection: Selection | None = None
) -> tuple[list[JobExecution], Path, dict]:
    selection = selection or Selection()
    context, adapter, capacity = _components(defn)
    plan = load_plan(defn)
    jobs = [Job(**item) for item in plan["jobs"]]
    selected, selection_meta = select_jobs(jobs, selection)

    run_id = _timestamp_id(str(context["name"]))
    run_root = Path(context["paths"]["run_root"])
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    write_json(run_dir / "context.json", context)
    write_json(run_dir / "plan.json", plan)
    run_record = {
        "schema_version": 1,
        "run_id": run_id,
        "name": context["name"],
        "status": "RUNNING",
        "started_at": _now(),
        "finished_at": None,
        "duration_s": None,
        "selection": selection_meta,
        "scheduler": {
            "capacity_provider": context["scheduler"]["capacity_provider"],
            "max_parallel": context["scheduler"]["max_parallel"],
            "poll_interval_s": context["scheduler"]["poll_interval_s"],
        },
    }
    write_json(run_dir / "run.json", run_record)

    scheduler = context["scheduler"]
    started = time.monotonic()
    try:
        executions = run_jobs(
            selected,
            lambda job: adapter.execute(context, job),
            capacity,
            int(scheduler["max_parallel"]),
            float(scheduler["poll_interval_s"]),
        )
        write_json(run_dir / "executions.json", [item.to_dict() for item in executions])
        run_record["status"] = "EXECUTED"
        return_value = executions
    except Exception as exc:
        run_record["status"] = "ERROR"
        run_record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        run_record["finished_at"] = _now()
        run_record["duration_s"] = time.monotonic() - started
        write_json(run_dir / "run.json", run_record)
        write_json(
            metadata_path(defn) / "last_run.json",
            {"run_dir": str(run_dir.resolve())},
        )
        update_state(
            defn,
            last_run_dir=str(run_dir.resolve()),
            last_run_at=run_record["finished_at"],
        )

    return return_value, run_dir, selection_meta


def _resolve_run_dir(defn: dict[str, Any], run_dir: str | Path | None) -> Path:
    if run_dir is not None:
        path = Path(run_dir).resolve()
    else:
        pointer = metadata_path(defn) / "last_run.json"
        if not pointer.exists():
            raise RuntimeError("no previous run; run 'reg run' first or pass --run-dir")
        path = Path(read_json(pointer)["run_dir"])
    if not path.is_dir():
        raise FileNotFoundError(f"run directory not found: {path}")
    return path


def _validate_results(
    executions: list[JobExecution], tests: list[TestResult]
) -> list[TestResult]:
    expected_ids = [item.job_id for item in executions]
    result_ids = [item.id for item in tests]

    if len(result_ids) != len(set(result_ids)):
        raise ValueError("adapter returned duplicate result IDs")
    if set(result_ids) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(result_ids))
        extra = sorted(set(result_ids) - set(expected_ids))
        raise ValueError(f"adapter result IDs do not match executions; missing={missing}, extra={extra}")

    for test in tests:
        test.status = str(test.status).upper()
        if test.status not in _CANONICAL_STATUSES:
            raise ValueError(
                f"adapter returned invalid status {test.status!r} for test {test.id!r}"
            )
    return tests


def collect(
    defn: dict[str, Any], run_dir: str | Path | None = None
) -> tuple[dict[str, Any], Path]:
    run_path = _resolve_run_dir(defn, run_dir)
    context = read_json(run_path / "context.json")
    run_record = read_json(run_path / "run.json")
    if run_record.get("status") not in {"EXECUTED", "COLLECTED"}:
        raise RuntimeError(
            f"run is not collectable; status={run_record.get('status')!r}: {run_path}"
        )

    executions_path = run_path / "executions.json"
    if not executions_path.exists():
        raise RuntimeError(f"execution evidence not found: {executions_path}")

    adapter = load_adapter(str(context["execution"]["adapter"]))
    raw_executions = read_json(executions_path)
    executions = [JobExecution(**item) for item in raw_executions]
    tests = _validate_results(executions, adapter.collect(context, executions))

    counts = {
        status: sum(test.status == status for test in tests)
        for status in ("PASS", "FAIL", "ERROR", "SKIP")
    }
    result = {
        "schema_version": 1,
        "run_id": run_record["run_id"],
        "name": context["name"],
        "generated_at": _now(),
        "started_at": run_record.get("started_at"),
        "finished_at": run_record.get("finished_at"),
        "duration_s": run_record.get("duration_s"),
        "status": "PASS" if counts["FAIL"] == counts["ERROR"] == 0 else "FAIL",
        "summary": {
            "total": len(tests),
            "pass": counts["PASS"],
            "fail": counts["FAIL"],
            "error": counts["ERROR"],
            "skip": counts["SKIP"],
        },
        "tests": [test.to_dict() for test in tests],
    }
    write_json(run_path / "result.json", result)

    run_record["status"] = "COLLECTED"
    run_record["collected_at"] = result["generated_at"]
    run_record["result_status"] = result["status"]
    write_json(run_path / "run.json", run_record)
    write_json(
        metadata_path(defn) / "last_result.json",
        {"result": str((run_path / "result.json").resolve())},
    )
    update_state(defn, last_result=str((run_path / "result.json").resolve()))
    return result, run_path
