from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mockingbird.adapter_utils import execution_path_refs, result_from_execution, run_process
from mockingbird.contracts import ExecutionAdapter
from mockingbird.models import CheckResult, ExecutionContext, Job, JobExecution, TestResult


_CANONICAL_STATUSES = {"PASS", "FAIL", "ERROR", "SKIP"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_argv(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"{field} must be a non-empty list of strings")
    return list(value)


def _config(context: dict[str, Any]) -> dict[str, Any]:
    config = context["execution"].get("config", {})
    if not isinstance(config, dict):
        raise ValueError("execution config must be a mapping")
    return config


def _jobs(config: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = config.get("jobs", [])
    if not isinstance(jobs, list):
        raise ValueError("execution.jobs must be a list")

    normalized: list[dict[str, Any]] = []
    for item in jobs:
        if isinstance(item, str):
            normalized.append({"id": item, "args": [item]})
        elif isinstance(item, dict):
            normalized.append(dict(item))
        else:
            raise ValueError("execution.jobs entries must be strings or mappings")
    return normalized


def _timeout(value: Any, *, field: str, required: bool = False) -> float | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    timeout_s = float(value)
    if timeout_s <= 0:
        raise ValueError(f"{field} must be > 0")
    return timeout_s


def _collector(config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    collect = config.get("collect")
    if not isinstance(collect, dict):
        raise ValueError("execution.collect must be a mapping")

    has_mode = "mode" in collect
    has_command = "command" in collect
    if has_mode == has_command:
        raise ValueError(
            "execution.collect requires exactly one of mode or command"
        )

    if has_mode:
        mode = str(collect["mode"])
        if mode != "exit-code":
            raise ValueError("execution.collect.mode must be 'exit-code'")
        return mode, collect

    _as_argv(collect.get("command"), field="execution.collect.command")
    _timeout(
        collect.get("timeout_s"),
        field="execution.collect.timeout_s",
        required=True,
    )
    return "command", collect


def _resolve_command(argv: list[str], cwd: Path) -> str | None:
    executable = argv[0]
    if "/" in executable:
        path = Path(executable)
        if not path.is_absolute():
            path = cwd / path
        return (
            str(path.resolve())
            if path.is_file() and os.access(path, os.X_OK)
            else None
        )
    return shutil.which(executable)


def _execution_context_from_observation(execution: JobExecution) -> ExecutionContext:
    observation = execution.observation if isinstance(execution.observation, dict) else {}
    stdout_path = observation.get("stdout_path")
    stderr_path = observation.get("stderr_path")
    if not stdout_path or not stderr_path:
        raise RuntimeError(
            f"command execution evidence is missing stdout/stderr paths for {execution.job_id!r}"
        )

    logs_dir = Path(stdout_path).resolve().parent
    job_dir = logs_dir.parent
    run_dir = job_dir.parent.parent
    return ExecutionContext(
        run_id=run_dir.name,
        run_dir=str(run_dir),
        job_dir=str(job_dir),
        workdir=str(job_dir / "work"),
        artifact_dir=str(job_dir / "artifacts"),
        logs_dir=str(logs_dir),
        stdout_path=str(Path(stdout_path).resolve()),
        stderr_path=str(Path(stderr_path).resolve()),
    )


class Adapter(ExecutionAdapter):
    """Declarative execution for projects that already expose commands."""

    def probe(self, context):
        config = _config(context)
        cwd = Path(context["invocation_dir"])
        checks: list[CheckResult] = []

        try:
            command = _as_argv(config.get("command"), field="execution.command")
            default_timeout = _timeout(
                config.get("timeout_s"),
                field="execution.timeout_s",
                required=True,
            )
            jobs = _jobs(config)
            for item in jobs:
                if not item.get("id"):
                    raise ValueError("every execution job requires id")
                args = item.get("args")
                if args is None:
                    args = [str(item["id"])]
                if not isinstance(args, list) or not all(
                    isinstance(arg, str) for arg in args
                ):
                    raise ValueError(
                        f"job {item.get('id')!r} args must be a list of strings"
                    )
                _timeout(
                    item.get("timeout_s", default_timeout),
                    field="timeout_s",
                    required=True,
                )
            collector_kind, collect = _collector(config)
        except Exception as exc:
            return [
                CheckResult(
                    "execution",
                    "contract",
                    "FAIL",
                    f"{type(exc).__name__}: {exc}",
                )
            ]

        resolved = _resolve_command(command, cwd)
        checks.append(
            CheckResult(
                "execution",
                "command",
                "PASS" if resolved else "FAIL",
                resolved or f"command not found: {command[0]}",
            )
        )

        if collector_kind == "command":
            collect_command = _as_argv(
                collect.get("command"),
                field="execution.collect.command",
            )
            resolved_collect = _resolve_command(collect_command, cwd)
            checks.append(
                CheckResult(
                    "execution",
                    "collect-command",
                    "PASS" if resolved_collect else "FAIL",
                    resolved_collect
                    or f"command not found: {collect_command[0]}",
                )
            )
        return checks

    def setup(self, context):
        Path(context["paths"]["adapter_workdir"]).mkdir(parents=True, exist_ok=True)

    def plan(self, context):
        config = _config(context)
        _as_argv(config.get("command"), field="execution.command")
        default_timeout = _timeout(
            config.get("timeout_s"),
            field="execution.timeout_s",
            required=True,
        )
        _collector(config)

        jobs = []
        for item in _jobs(config):
            job_id = str(item.get("id", ""))
            args = item.get("args")
            if args is None:
                args = [job_id]
            if not isinstance(args, list) or not all(
                isinstance(arg, str) for arg in args
            ):
                raise ValueError(f"job {job_id!r} args must be a list of strings")
            timeout_s = _timeout(
                item.get("timeout_s", default_timeout),
                field=f"job {job_id!r} timeout_s",
                required=True,
            )
            jobs.append(
                Job(
                    id=job_id,
                    payload={
                        "args": list(args),
                        "timeout_s": timeout_s,
                    },
                    metadata=dict(item.get("metadata", {})),
                )
            )
        return jobs

    def execute(self, context, job, execution: ExecutionContext):
        config = _config(context)
        command = _as_argv(config.get("command"), field="execution.command")
        args = list(job.payload.get("args", []))
        started_at = _now()
        process = run_process(
            [*command, *args],
            execution,
            cwd=context["invocation_dir"],
            timeout_s=float(job.payload["timeout_s"]),
        )
        return JobExecution(
            job_id=job.id,
            started_at=started_at,
            finished_at=_now(),
            duration_s=process.duration_s,
            observation=process.to_observation(),
        )

    def collect(self, context, executions):
        config = _config(context)
        collector_kind, collect = _collector(config)

        if collector_kind == "exit-code":
            return [self._collect_from_exit_code(item) for item in executions]

        collect_command = _as_argv(
            collect.get("command"),
            field="execution.collect.command",
        )
        timeout_s = _timeout(
            collect.get("timeout_s"),
            field="execution.collect.timeout_s",
            required=True,
        )
        return [
            self._collect_with_command(
                context,
                execution,
                collect_command,
                float(timeout_s),
            )
            for execution in executions
        ]

    def _collect_from_exit_code(self, execution: JobExecution) -> TestResult:
        observation = execution.observation if isinstance(execution.observation, dict) else {}
        timed_out = bool(observation.get("timed_out", False))
        try:
            returncode = int(observation["returncode"])
        except (KeyError, TypeError, ValueError):
            return result_from_execution(
                execution,
                "ERROR",
                reason="execution return code is unavailable",
                artifacts=execution_path_refs(execution, "stdout", "stderr"),
            )

        if timed_out:
            status = "ERROR"
            reason = "execution timeout"
        else:
            status = "PASS" if returncode == 0 else "FAIL"
            reason = None if returncode == 0 else f"exit={returncode}"

        return result_from_execution(
            execution,
            status,
            reason=reason,
            artifacts=execution_path_refs(execution, "stdout", "stderr"),
        )

    def _collect_with_command(
        self,
        context: dict[str, Any],
        execution: JobExecution,
        command: list[str],
        timeout_s: float,
    ) -> TestResult:
        execution_context = _execution_context_from_observation(execution)
        process = run_process(
            [*command, execution.job_id],
            execution_context,
            cwd=context["invocation_dir"],
            timeout_s=timeout_s,
            log_name="collect",
        )

        if process.timed_out:
            return result_from_execution(
                execution,
                "ERROR",
                reason="collector timeout",
                artifacts=[process.stdout_path, process.stderr_path],
            )
        if process.returncode != 0:
            return result_from_execution(
                execution,
                "ERROR",
                reason=f"collector exit={process.returncode}",
                artifacts=[process.stdout_path, process.stderr_path],
            )

        try:
            payload = json.loads(Path(process.stdout_path).read_text())
            if not isinstance(payload, dict):
                raise ValueError("collector output must be one JSON object")
            status = str(payload["status"]).upper()
            if status not in _CANONICAL_STATUSES:
                raise ValueError(f"invalid collector status: {status!r}")
            artifacts = payload.get("artifacts", [])
            if not isinstance(artifacts, list) or any(
                not isinstance(item, str) for item in artifacts
            ):
                raise ValueError("collector artifacts must be list[str]")
            metadata = payload.get("metadata", {})
            if not isinstance(metadata, dict):
                raise ValueError("collector metadata must be a mapping")
            reason = payload.get("reason")
            if reason is not None and not isinstance(reason, str):
                raise ValueError("collector reason must be a string or null")
        except Exception as exc:
            return result_from_execution(
                execution,
                "ERROR",
                reason=f"invalid collector output: {type(exc).__name__}: {exc}",
                artifacts=[process.stdout_path, process.stderr_path],
            )

        return result_from_execution(
            execution,
            status,
            artifacts=artifacts,
            reason=reason,
            metadata=metadata,
        )
