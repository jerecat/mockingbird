"""Read saved evidence without invoking executors or collectors."""
from .context import metadata_path, run_root_path, validate_definition_identity
from .errors import PrerequisiteError
from .io import read_json
from .lifecycle import _resolve_run_dir, saved_run_context


def snapshot(defn, run_dir=None):
    root = _resolve_run_dir(defn, run_dir)
    context = saved_run_context(root)
    validate_definition_identity(defn, context)
    run = read_json(root / "run.json")
    def optional(name):
        path = root / name
        return read_json(path) if path.exists() else {}
    progress = optional("progress.json")
    sweep = optional("collection_progress.json")
    per_job = run.get("checkpoint_storage") == "per-job"
    legacy_executions = {}
    legacy_collection = {}
    if not per_job:
        legacy_executions = {e["job_id"]: e for e in optional("executions.json") or []}
        legacy_collection = optional("collection.json").get("jobs", {})
    journal = optional("collection.json")
    refreshed = "collectors" in journal
    jobs = []
    for job_id in run["selection"]["selected_ids"]:
        folder = run["jobs"][job_id]["job_dir"]
        if per_job:
            execution = optional(f"{folder}/execution.json")
            entry = (journal["jobs"].get(job_id, {}) if refreshed else
                     optional(f"{folder}/collection.json").get("entry", {}))
        else:
            execution = legacy_executions.get(job_id, {})
            entry = legacy_collection.get(job_id, {})
        state = "RECORDED" if execution else "NOT_RECORDED"
        if not execution and progress.get("job_id") == job_id:
            state = progress["state"]
        result = entry.get("result", {})
        jobs.append({"id": job_id, "execution": state,
                     "collection": entry.get("state", "UNCOLLECTED"),
                     "verdict": result.get("status"),
                     "reason": result.get("reason") or entry.get("reason"),
                     "observed_at": entry.get("updated_at")})
    return {"plan": context.get("plan", context.get("name")),
            "run_id": run["run_id"], "run_dir": str(root),
            "execution_status": run["status"], "total": len(jobs),
            "recorded": sum(j["execution"] == "RECORDED" for j in jobs),
            "final": sum(j["collection"] == "COMPLETE" for j in jobs),
            "collection_counts": {state: sum(j["collection"] == state for j in jobs)
                                  for state in ("COMPLETE", "PENDING", "ERROR", "UNCOLLECTED")},
            "last_execution_update": run.get("finished_at") or progress.get("updated_at") or run.get("started_at"),
            "collection_sweep": sweep, "jobs": jobs}


def history(defn):
    """List existing run evidence; no current YAML or prepared context needed."""
    rows = []
    for path in run_root_path(defn).glob('*/run.json'):
        record = read_json(path)
        validate_definition_identity(defn, record)
        result_path = path.parent / 'result.json'
        result = read_json(result_path) if result_path.exists() else {}
        rows.append({'run_id': record['run_id'], 'run_dir': str(path.parent),
                     'started_at': record['started_at'], 'execution': record['status'],
                     'result': result.get('status'), 'summary': result.get('summary'),
                     'jobs': len(record['selection']['selected_ids'])})
    rows.sort(key=lambda row: (row['started_at'], row['run_id']), reverse=True)
    return {'plan': defn['plan'], 'runs': rows}


def plan_details(defn, run_dir=None):
    if run_dir is None:
        path = metadata_path(defn) / 'plan.json'
        if not path.is_file():
            raise PrerequisiteError('plan not created', 'plan')
        plan = read_json(path)
        validate_definition_identity(defn, plan)
    else:
        root = _resolve_run_dir(defn, run_dir)
        validate_definition_identity(defn, saved_run_context(root))
        plan = read_json(root / 'plan.json')
    return plan
