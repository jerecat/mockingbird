"""Resolve the optional synchronous setup command list at prepare time."""
from .command_fields import mapping, argv, timeout
from .models import Job
from .validation import validate_jobs


def resolve_setup(value):
    config = mapping(value, "setup", {"defaults", "jobs"})
    fields = {"command", "args", "timeout_s"}
    defaults = mapping(config.get("defaults", {}), "setup.defaults", fields)
    # Validate defaults even when no Job uses them.
    if "command" in defaults:
        argv(defaults["command"], "setup.defaults.command")
    if "args" in defaults:
        argv(defaults["args"], "setup.defaults.args", empty=True)
    if "timeout_s" in defaults:
        timeout(defaults["timeout_s"], "setup.defaults.timeout_s")
    raw_jobs = config.get("jobs", [])
    if not isinstance(raw_jobs, list):
        raise ValueError("setup.jobs must be a list")
    jobs = []
    for raw in raw_jobs:
        item = mapping({"id": raw} if isinstance(raw, str) else raw, "setup job", fields | {"id"})
        job_id = item.get("id")
        resolved = dict(defaults)
        resolved.update({key: val for key, val in item.items() if key in fields})
        jobs.append(Job(job_id, {
            "command": argv(resolved.get("command"), "setup.command"),
            "args": argv(resolved.get("args", [job_id]), "setup.args", empty=True),
            "timeout_s": timeout(resolved.get("timeout_s"), "setup.timeout_s"),
        }))
    validate_jobs(jobs)
    return {"jobs": [job.to_dict() for job in jobs]}


def setup_required(context):
    # Custom adapters retain their original setup hook requirement.
    return bool(context.get("setup", {}).get("jobs")) or context["execution"]["adapter"] != "command"
