from __future__ import annotations

import copy
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from mockingbird.adapter_utils import result_from_execution, run_process
from mockingbird.contracts import ExecutionAdapter
from mockingbird.models import CollectionAttempt, CheckResult, ExecutionContext, Job, JobExecution
from mockingbird.command_fields import mapping as _mapping, argv as _argv, timeout as _timeout


_FINAL_STATUSES = {"PASS", "FAIL", "ERROR", "SKIP"}
_FIELDS = {"command", "args", "timeout_s", "collect"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collector(value, job_id):
    value = _mapping(value, "collect", {"mode", "command", "args", "timeout_s"})
    if "mode" in value:
        if value != {"mode": "no-check"}:
            raise ValueError("collect.mode supports only no-check; use a collector command for judgement")
        return dict(value)
    return {
        "command": _argv(value.get("command"), "collect.command"),
        "args": _argv(value.get("args", [job_id]), "collect.args", empty=True),
        "timeout_s": _timeout(value.get("timeout_s"), "collect.timeout_s"),
    }


def _resolve_command(argv, cwd):
    executable = argv[0]
    if "/" in executable:
        path = Path(executable)
        if not path.is_absolute():
            path = cwd / path
        return str(path.resolve()) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(executable)


class Adapter(ExecutionAdapter):
    """Expand declarative contracts at plan time; never infer test outcomes."""

    def plan(self, context):
        config = _mapping(context["execution"].get("config", {}), "execution", _FIELDS | {"defaults", "jobs"})
        # Top-level common fields remain supported as shorthand defaults.
        defaults = {key: value for key, value in config.items() if key in _FIELDS}
        explicit = _mapping(config.get("defaults", {}), "execution.defaults", _FIELDS)
        if set(defaults) & set(explicit):
            raise ValueError("declare a default either at execution level or under defaults, not both")
        defaults.update(explicit)
        raw_jobs = config.get("jobs", [])
        if not isinstance(raw_jobs, list):
            raise ValueError("execution.jobs must be a list")
        jobs = []
        seen = set()
        for raw in raw_jobs:
            item = {"id": raw} if isinstance(raw, str) else raw
            item = _mapping(item, "job", _FIELDS | {"id", "metadata"})
            job_id = item.get("id")
            if not isinstance(job_id, str) or not job_id or job_id != job_id.strip():
                raise ValueError("job ID must be a non-empty string without surrounding whitespace")
            if len(job_id) > 512 or any(ord(ch) < 32 or ord(ch) == 127 for ch in job_id):
                raise ValueError("job ID has control characters or is too long")
            if job_id in seen:
                raise ValueError(f"duplicate job ID: {job_id}")
            seen.add(job_id)
            resolved = copy.deepcopy(defaults)
            resolved.update(copy.deepcopy({k: v for k, v in item.items() if k in _FIELDS}))
            payload = {
                "command": _argv(resolved.get("command"), f"job {job_id!r} command"),
                "args": _argv(resolved.get("args", [job_id]), "args", empty=True),
                "timeout_s": _timeout(resolved.get("timeout_s"), f"job {job_id!r} timeout_s"),
                "collect": _collector(resolved.get("collect", {"mode": "no-check"}), job_id),
            }
            metadata = item.get("metadata", {})
            if not isinstance(metadata, dict):
                raise ValueError("job metadata must be a mapping")
            job = Job(job_id, payload, copy.deepcopy(metadata))
            json.dumps(job.to_dict(), allow_nan=False)
            jobs.append(job)
        return jobs

    def probe(self, context):
        try:
            jobs = self.plan(context)
        except Exception as exc:
            return [CheckResult("execution", "contract", "FAIL", f"{type(exc).__name__}: {exc}")]
        checks = []
        for job in jobs:
            commands = [("command", job.payload["command"])]
            collect = job.payload["collect"]
            if "command" in collect:
                commands.append(("collect-command", collect["command"]))
            for kind, command in commands:
                resolved = _resolve_command(command, Path(context["invocation_dir"]))
                checks.append(CheckResult("execution", f"{job.id}:{kind}", "PASS" if resolved else "FAIL",
                                          resolved or f"command not found: {command[0]}"))
        return checks or [CheckResult("execution", "contract", "PASS", "valid empty plan")]

    def setup(self, context):
        Path(context["paths"]["adapter_workdir"]).mkdir(parents=True, exist_ok=True)

    def execute(self, context, job, execution: ExecutionContext):
        # Only the frozen Job payload supplies command, arguments and timeout.
        contract = job.payload
        started_at = _now()
        observation = {"execution_context": execution.to_dict()}
        try:
            process = run_process([*contract["command"], *contract["args"]], execution,
                                  cwd=context["invocation_dir"], timeout_s=contract["timeout_s"],
                                  env=dict(os.environ, MB_JOB_ID=job.id, MB_RUN_ID=execution.run_id))
            observation.update(process.to_observation())
            duration = process.duration_s
        except OSError as exc:
            observation["launch_error"] = f"{type(exc).__name__}: {exc}"
            duration = (datetime.now(timezone.utc) - datetime.fromisoformat(started_at)).total_seconds()
        return JobExecution(job.id, started_at, _now(), duration, observation,
                            contract=job.to_dict(), run_id=execution.run_id)

    def collect(self, context, executions):
        outcomes = []
        for execution in executions:
            try:
                outcomes.append(self._collect_one(context, execution))
            except Exception as exc:
                outcomes.append(CollectionAttempt(execution.job_id, "ERROR", reason=f"{type(exc).__name__}: {exc}"))
        return outcomes

    def _collect_one(self, context, execution):
        collect = execution.contract["payload"]["collect"]
        if collect.get("mode") == "no-check":
            return result_from_execution(execution, "PASS", artifacts=[])
        execution_context = ExecutionContext(**execution.observation["execution_context"])
        # These environment variables are part of the external command contract.
        # No external scheduler IDs or artifact locations are interpreted by MB.
        env = dict(os.environ, MB_JOB_ID=execution.job_id, MB_RUN_ID=execution.run_id)
        process = run_process([*collect["command"], *collect["args"]], execution_context,
                              cwd=context["invocation_dir"], env=env, timeout_s=collect["timeout_s"],
                              log_name=f"collect-{uuid4().hex}")
        artifacts = [process.stdout_path, process.stderr_path]
        if process.timed_out or process.returncode != 0:
            return CollectionAttempt(execution.job_id, "ERROR", reason="collector timeout" if process.timed_out else f"collector exit={process.returncode}", artifacts=artifacts)
        try:
            payload = json.loads(Path(process.stdout_path).read_text())
            if not isinstance(payload, dict):
                raise ValueError("collector output must be one JSON object")
            if "id" in payload and payload["id"] != execution.job_id:
                raise ValueError("collector result ID does not match Job ID")
            status = payload["status"]
            if status not in _FINAL_STATUSES | {"PENDING"}:
                raise ValueError(f"invalid collector status: {status!r}")
            refs = payload.get("artifacts", [])
            if not isinstance(refs, list) or any(not isinstance(v, str) for v in refs):
                raise ValueError("collector artifacts must be list[str]")
            reason = payload.get("reason")
            if reason is not None and not isinstance(reason, str):
                raise ValueError("collector reason must be a string or null")
            metadata = payload.get("metadata", {})
            if not isinstance(metadata, dict):
                raise ValueError("collector metadata must be a mapping")
        except Exception as exc:
            return CollectionAttempt(execution.job_id, "ERROR", reason=f"invalid collector output: {exc}", artifacts=artifacts)
        if status == "PENDING":
            return CollectionAttempt(execution.job_id, "PENDING", reason=reason, artifacts=refs)
        return result_from_execution(execution, status, artifacts=refs, reason=reason, metadata=metadata)
