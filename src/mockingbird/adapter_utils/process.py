from __future__ import annotations

import math
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from mockingbird.models import ExecutionContext


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    timed_out: bool
    stdout_path: str
    stderr_path: str
    duration_s: float

    def to_observation(self) -> dict:
        return asdict(self)


def _log_paths(execution: ExecutionContext, log_name: str | None) -> tuple[Path, Path]:
    if log_name is None:
        return Path(execution.stdout_path), Path(execution.stderr_path)
    if not log_name or any(ch in log_name for ch in "/\\\0\n\r"):
        raise ValueError("log_name must be a simple non-empty file-name component")
    logs = Path(execution.logs_dir)
    return logs / f"{log_name}.stdout.log", logs / f"{log_name}.stderr.log"


def _terminate_process_group(process: subprocess.Popen, grace_s: float) -> None:
    deadline = time.monotonic() + grace_s
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return
    try:
        process.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        pass
    # Parent exit is not proof of group exit. Give surviving group members
    # the remaining grace period, then kill the group even if parent exited.
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(min(0.01, max(0, deadline - time.monotonic())))
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        process.wait()
        return
    process.wait()


def run_process(
    argv: Sequence[str],
    execution: ExecutionContext,
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout_s: float | None = None,
    terminate_grace_s: float = 5.0,
    log_name: str | None = None,
) -> ProcessResult:
    """Run one adapter-owned process without buffering stdout/stderr in memory.

    This utility intentionally has no ``shell=True`` mode. If shell semantics
    are required, put them in a project-owned wrapper script and execute that
    script explicitly.
    """

    args = [str(item) for item in argv]
    if not args:
        raise ValueError("argv must not be empty")
    if timeout_s is not None and (isinstance(timeout_s, bool) or not math.isfinite(timeout_s) or timeout_s <= 0):
        raise ValueError("timeout_s must be > 0")
    if isinstance(terminate_grace_s, bool) or not math.isfinite(terminate_grace_s) or terminate_grace_s < 0:
        raise ValueError("terminate_grace_s must be >= 0")

    stdout_path, stderr_path = _log_paths(execution, log_name)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    actual_cwd = Path(cwd) if cwd is not None else Path(execution.workdir)
    actual_cwd.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    timed_out = False
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            args,
            cwd=actual_cwd,
            env=None if env is None else dict(env),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            shell=False,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_group(process, terminate_grace_s)
            returncode = process.returncode
        except BaseException:
            _terminate_process_group(process, terminate_grace_s)
            raise

    return ProcessResult(
        returncode=int(returncode),
        timed_out=timed_out,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        duration_s=time.monotonic() - started,
    )
