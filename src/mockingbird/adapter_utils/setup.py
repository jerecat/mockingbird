"""Synchronous preparation boundary: exit zero is success, no test judgement."""
import os
from datetime import datetime, timezone
from pathlib import Path

from .process import run_process
from mockingbird.io import write_json
from mockingbird.models import ExecutionContext


def execute_setup_job(context, job, execution: ExecutionContext):
    record = {"job_id": job.id, "contract": job.to_dict(), "started_at": datetime.now(timezone.utc).isoformat(),
              "status": "RUNNING", "stdout_path": execution.stdout_path, "stderr_path": execution.stderr_path}
    path = Path(execution.job_dir) / "execution.json"
    write_json(path, record)
    try:
        result = run_process([*job.payload["command"], *job.payload["args"]], execution,
                             cwd=context["invocation_dir"], timeout_s=job.payload["timeout_s"],
                             env=dict(os.environ, MB_SETUP_ID=execution.run_id, MB_JOB_ID=job.id))
        record["observation"] = result.to_observation()
        record["status"] = "SUCCEEDED" if result.returncode == 0 and not result.timed_out else "FAILED"
        if record["status"] == "FAILED":
            reason = "timed out" if result.timed_out else f"exit={result.returncode}"
            raise RuntimeError(f"setup Job {job.id!r} failed ({reason}); inspect {execution.logs_dir}")
    except BaseException as exc:
        record["status"] = "INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "FAILED"
        record["error"] = str(exc) or type(exc).__name__
        raise
    finally:
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(path, record)
    return record
