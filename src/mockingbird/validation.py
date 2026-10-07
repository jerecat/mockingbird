"""Small boundary checks shared by runtime and the conformance kit."""
import json
import math
from .models import CollectionAttempt, TestResult

FINAL_STATUSES = {"PASS", "FAIL", "ERROR", "SKIP"}


def positive_seconds(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field} must be a finite positive number")
    return float(value)


def capacity_slots(value):
    if type(value) is not int or value < 0:
        raise ValueError("available_slots must return a non-negative int (not bool)")
    return value


def validate_jobs(jobs):
    ids = set()
    for job in jobs:
        value = job.id
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("job ID must be a non-empty string without surrounding whitespace")
        if len(value) > 512 or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ValueError("job ID is too long or contains control characters")
        if value in ids:
            raise ValueError("adapter returned duplicate job IDs")
        ids.add(value)
        json.dumps(job.to_dict(), allow_nan=False)


def bind_execution(result, job, execution):
    if result.job_id != job.id:
        raise ValueError(f"adapter returned execution for {result.job_id!r}; expected {job.id!r}")
    result.paths = execution.evidence_paths()
    result.contract = job.to_dict()
    result.run_id = execution.run_id
    json.dumps(result.to_dict(), allow_nan=False)
    return result


def validate_outcome(outcome, job_id):
    if not isinstance(outcome, (CollectionAttempt, TestResult)):
        raise ValueError("collector returned an invalid outcome type")
    if outcome.id != job_id:
        raise ValueError("collector outcome ID does not match the requested Job")
    if isinstance(outcome, CollectionAttempt):
        if outcome.state not in {"PENDING", "ERROR"}:
            raise ValueError("invalid collection state")
    else:
        outcome.status = str(outcome.status).upper()
        if outcome.status not in FINAL_STATUSES:
            raise ValueError(f"adapter returned invalid status {outcome.status!r}")
    if not isinstance(outcome.artifacts, list) or any(not isinstance(v, str) for v in outcome.artifacts):
        raise ValueError("artifacts must be list[str]")
    if outcome.reason is not None and not isinstance(outcome.reason, str):
        raise ValueError("reason must be a string or null")
    json.dumps(outcome.to_dict(), allow_nan=False)
