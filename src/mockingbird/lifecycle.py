from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import load_context, load_state, metadata_path, update_state, validate_definition_identity
from .io import collection_lock, read_json, write_json
from .models import ExecutionContext, Job, JobExecution, TestResult
from .plugins import load_adapter, load_capacity_provider
from .scheduler import run_jobs, validate_max_parallel
from .selection import Selection, select_jobs
from .validation import FINAL_STATUSES, bind_execution, positive_seconds, validate_jobs, validate_outcome


_CANONICAL_STATUSES = FINAL_STATUSES


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


def _job_directory_name(index: int, job_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", job_id).strip("._-") or "job"
    slug = slug[:64]
    digest = hashlib.sha256(job_id.encode()).hexdigest()[:10]
    return f"{index:04d}_{slug}_{digest}"


def _execution_context(run_id: str, run_dir: Path, index: int, job: Job) -> ExecutionContext:
    job_dir = run_dir / "jobs" / _job_directory_name(index, job.id)
    workdir = job_dir / "work"
    artifact_dir = job_dir / "artifacts"
    logs_dir = job_dir / "logs"
    for path in (job_dir, workdir, artifact_dir, logs_dir):
        path.mkdir(parents=True, exist_ok=True)
    return ExecutionContext(
        run_id=run_id,
        run_dir=str(run_dir.resolve()),
        job_dir=str(job_dir.resolve()),
        workdir=str(workdir.resolve()),
        artifact_dir=str(artifact_dir.resolve()),
        logs_dir=str(logs_dir.resolve()),
        stdout_path=str((logs_dir / "stdout.log").resolve()),
        stderr_path=str((logs_dir / "stderr.log").resolve()),
    )


def setup(defn: dict[str, Any]) -> None:
    context, adapter, _ = _components(defn)
    adapter.setup(context)
    update_state(defn, setup_at=_now(), setup_context_prepared_at=context["prepared_at"])


def create_plan(defn: dict[str, Any]) -> dict[str, Any]:
    state = load_state(defn)
    context = load_context(defn)
    if state.get("setup_context_prepared_at") != context["prepared_at"]:
        raise RuntimeError("setup is missing or stale; run 'mockingbird setup' first")

    adapter = load_adapter(str(context["execution"]["adapter"]))
    plan_path = metadata_path(defn) / "plan.json"
    try:
        jobs = adapter.plan(context)
        validate_jobs(jobs)
    except Exception:
        plan_path.unlink(missing_ok=True)
        raise

    plan = {
        "schema_version": 2,
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
        raise RuntimeError("plan not created; run 'mockingbird plan' first")
    plan = read_json(path)
    if plan.get("schema_version") != 2:
        raise RuntimeError("plan schema is obsolete; run mockingbird plan again")
    context = load_context(defn)
    if plan.get("context_prepared_at") != context.get("prepared_at"):
        raise RuntimeError("plan is stale for the current context; run 'mockingbird setup' and 'mockingbird plan'")
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
    validate_max_parallel(context["scheduler"]["max_parallel"])
    positive_seconds(context["scheduler"]["poll_interval_s"], "scheduler.poll_interval_s")
    plan = load_plan(defn)
    jobs = [Job(**item) for item in plan["jobs"]]
    selected, selection_meta = select_jobs(jobs, selection)

    run_id = _timestamp_id(str(context["name"]))
    run_root = Path(context["paths"]["run_root"])
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    execution_contexts = {
        job.id: _execution_context(run_id, run_dir, index, job)
        for index, job in enumerate(selected, start=1)
    }

    write_json(run_dir / "context.json", context)
    write_json(run_dir / "plan.json", plan)
    run_record = {
        "schema_version": 2,
        "run_id": run_id,
        "checkpoint_storage": "per-job",
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
        "jobs": {
            job.id: execution_contexts[job.id].evidence_paths()
            for job in selected
        },
    }
    write_json(run_dir / "run.json", run_record)

    scheduler = context["scheduler"]
    started = time.monotonic()

    completed: list[JobExecution] = []

    def execute(job: Job) -> JobExecution:
        execution_context = execution_contexts[job.id]
        job_started = _now()
        began = time.monotonic()
        error = None
        try:
            result = adapter.execute(context, job, execution_context)
            bind_execution(result, job, execution_context)
        except Exception as exc:
            error = exc
            result = JobExecution(job.id, job_started, _now(), time.monotonic() - began,
                                  observation={"executor_error": f"{type(exc).__name__}: {exc}"})
            bind_execution(result, job, execution_context)
        # Persist each returned execution before the scheduler consumes it.
        write_json(Path(execution_context.job_dir) / "execution.json", result.to_dict())
        completed.append(result)
        if error is not None:
            raise error
        return result

    try:
        executions = run_jobs(
            selected,
            execute,
            capacity,
            scheduler["max_parallel"],
            scheduler["poll_interval_s"],
        )
        run_record["status"] = "EXECUTED"
        return_value = executions
    except KeyboardInterrupt:
        # The scheduler stops dispatch and drains in-flight execute calls before
        # unwinding. Their saved evidence remains available for collection.
        run_record["status"] = "INTERRUPTED"
        run_record["error"] = "KeyboardInterrupt: execution interrupted by operator"
        raise
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
        # Derived view only; collection never depends on its successful write.
        write_json(run_dir / "executions.json", [item.to_dict() for item in completed])

    return return_value, run_dir, selection_meta


def _resolve_run_dir(defn: dict[str, Any], run_dir: str | Path | None) -> Path:
    if run_dir is not None:
        path = Path(run_dir).resolve()
    else:
        pointer = metadata_path(defn) / "last_run.json"
        if not pointer.exists():
            raise RuntimeError("no previous run; run 'mockingbird run' first or pass --run-dir")
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
        validate_outcome(test, test.id)
    return tests


def collect(
    defn: dict[str, Any], run_dir: str | Path | None = None
) -> tuple[dict[str, Any], Path]:
    run_path = _resolve_run_dir(defn, run_dir)
    with collection_lock(run_path):
        return _collect_locked(defn, run_path)


def _collect_locked(defn, run_path):
    context = read_json(run_path / "context.json")
    validate_definition_identity(defn, context)
    run_record = read_json(run_path / "run.json")
    if run_record.get("status") not in {"EXECUTED", "COLLECTED", "ERROR", "INTERRUPTED"}:
        raise RuntimeError(f"run is not collectable; status={run_record.get('status')!r}: {run_path}")
    if run_record.get("schema_version") != 2:
        raise RuntimeError("run schema is obsolete; use the previous version to collect this run")
    per_job = run_record.get("checkpoint_storage") == "per-job"
    selected = run_record["selection"]["selected_ids"]
    job_dirs = {job_id: run_path / run_record["jobs"][job_id]["job_dir"] for job_id in selected}
    if per_job:
        executions = []
        for job_id in selected:
            path = job_dirs[job_id] / "execution.json"
            if path.exists():
                item = JobExecution(**read_json(path))
                if item.job_id != job_id:
                    raise ValueError("execution ID does not match its Job directory")
                executions.append(item)
    else:
        # Existing schema-2 runs retain their original checkpoint format.
        executions = [JobExecution(**item) for item in read_json(run_path / "executions.json")]
    by_id = {item.job_id: item for item in executions}
    if len(by_id) != len(executions) or not set(by_id).issubset(selected):
        raise ValueError("execution IDs do not match the run")
    if any(item.run_id != run_record["run_id"] for item in executions):
        raise ValueError("execution belongs to another run")

    journal_path = run_path / "collection.json"
    if not per_job and journal_path.exists():
        journal = read_json(journal_path)
        if journal["run_id"] != run_record["run_id"] or set(journal["jobs"]) != set(selected):
            raise ValueError("collection journal does not match the run")
    else:
        journal = {"schema_version": 2, "run_id": run_record["run_id"], "jobs": {
            job_id: {"state": "UNCOLLECTED", "attempts": 0} for job_id in selected
        }}
    if per_job:
        for job_id in selected:
            path = job_dirs[job_id] / "collection.json"
            if path.exists():
                checkpoint = read_json(path)
                if checkpoint["run_id"] != run_record["run_id"] or checkpoint["job_id"] != job_id:
                    raise ValueError("collection checkpoint does not match the run or Job")
                journal["jobs"][job_id] = checkpoint["entry"]
    adapter = load_adapter(str(context["execution"]["adapter"]))
    for job_id in selected:
        entry = journal["jobs"][job_id]
        if entry["state"] == "COMPLETE" or job_id not in by_id:
            continue
        execution = by_id[job_id]
        attempts = entry["attempts"] + 1
        try:
            outcomes = adapter.collect(context, [execution])
            if len(outcomes) != 1 or outcomes[0].id != job_id:
                raise ValueError("collector must return exactly one outcome for the requested Job ID")
            outcome = outcomes[0]
            validate_outcome(outcome, job_id)
            if isinstance(outcome, TestResult):
                entry = {"state": "COMPLETE", "result": outcome.to_dict()}
            else:
                entry = outcome.to_dict()
            json.dumps(entry, allow_nan=False)
        except Exception as exc:
            entry = {"state": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}
        entry.update(attempts=attempts, updated_at=_now())
        journal["jobs"][job_id] = entry
        if per_job:
            write_json(job_dirs[job_id] / "collection.json", {
                "run_id": run_record["run_id"], "job_id": job_id, "entry": entry})
        else:
            write_json(journal_path, journal)
    # Derived view for new runs, authoritative checkpoint for legacy runs.
    write_json(journal_path, journal)

    tests = [TestResult(**journal["jobs"][job_id]["result"]) for job_id in selected
             if journal["jobs"][job_id]["state"] == "COMPLETE"]
    _validate_results([by_id[test.id] for test in tests], tests)
    counts = {status: sum(test.status == status for test in tests) for status in _CANONICAL_STATUSES}
    states = [journal["jobs"][job_id]["state"] for job_id in selected]
    complete = len(tests) == len(selected)
    result = {
        "schema_version": 2,
        "run_id": run_record["run_id"],
        "name": context["name"],
        "generated_at": _now(),
        "started_at": run_record.get("started_at"),
        "finished_at": run_record.get("finished_at"),
        "duration_s": run_record.get("duration_s"),
        "status": ("PASS" if counts["FAIL"] == counts["ERROR"] == 0 else "FAIL") if complete else "PENDING",
        "collection_complete": complete,
        "summary": {
            "total": len(selected),
            "pass": counts["PASS"], "fail": counts["FAIL"],
            "error": counts["ERROR"], "skip": counts["SKIP"],
            "pending": states.count("PENDING"),
            "uncollected": states.count("UNCOLLECTED"),
            "collection_error": states.count("ERROR"),
        },
        "tests": [test.to_dict() for test in tests],
        "collection": journal["jobs"],
    }
    write_json(run_path / "result.json", result)
    # Execution status is preserved independently of collection status.
    run_record["collection_status"] = "COMPLETE" if complete else "PENDING"
    run_record["collected_at"] = result["generated_at"]
    run_record["result_status"] = result["status"]
    write_json(run_path / "run.json", run_record)
    write_json(metadata_path(defn) / "last_result.json", {"result": str((run_path / "result.json").resolve())})
    update_state(defn, last_result=str((run_path / "result.json").resolve()))
    return result, run_path
