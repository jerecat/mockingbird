from __future__ import annotations

from pathlib import Path

from mockingbird.adapters.command import Adapter
from mockingbird.models import ExecutionContext


def _execution_context(tmp_path: Path) -> ExecutionContext:
    run_dir = tmp_path / "runs" / "run"
    job_dir = run_dir / "jobs" / "job"
    workdir = job_dir / "work"
    artifact_dir = job_dir / "artifacts"
    logs_dir = job_dir / "logs"
    for path in (workdir, artifact_dir, logs_dir):
        path.mkdir(parents=True, exist_ok=True)
    return ExecutionContext(
        run_id="run",
        run_dir=str(run_dir),
        job_dir=str(job_dir),
        workdir=str(workdir),
        artifact_dir=str(artifact_dir),
        logs_dir=str(logs_dir),
        stdout_path=str(logs_dir / "stdout.log"),
        stderr_path=str(logs_dir / "stderr.log"),
    )


def test_string_job_runs_exactly_one_project_command_with_job_id(tmp_path):
    script = tmp_path / "run.sh"
    script.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> calls.txt\n"
    )
    script.chmod(0o755)

    context = {
        "invocation_dir": str(tmp_path),
        "paths": {"adapter_workdir": str(tmp_path / "work" / "exec")},
        "execution": {
            "adapter": "command",
            "config": {
                "command": ["./run.sh"],
                "timeout_s": 5,
                "jobs": ["job-a"],
                "collect": {"mode": "exit-code"},
            },
        },
    }

    adapter = Adapter()
    job = adapter.plan(context)[0]
    execution_context = _execution_context(tmp_path)
    execution = adapter.execute(context, job, execution_context)
    execution.paths = execution_context.evidence_paths()

    assert (tmp_path / "calls.txt").read_text().splitlines() == ["job-a"]
    assert execution.observation["returncode"] == 0
    result = adapter.collect(context, [execution])[0]
    assert result.id == "job-a"
    assert result.status == "PASS"


def test_mapping_job_can_override_arguments_and_timeout(tmp_path):
    script = tmp_path / "run.sh"
    script.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> calls.txt\n"
    )
    script.chmod(0o755)

    context = {
        "invocation_dir": str(tmp_path),
        "paths": {"adapter_workdir": str(tmp_path / "work" / "exec")},
        "execution": {
            "adapter": "command",
            "config": {
                "command": ["./run.sh"],
                "timeout_s": 5,
                "jobs": [
                    {
                        "id": "job-a",
                        "args": ["--test", "alpha"],
                        "timeout_s": 7,
                    }
                ],
                "collect": {"mode": "exit-code"},
            },
        },
    }

    adapter = Adapter()
    job = adapter.plan(context)[0]

    assert job.payload["args"] == ["--test", "alpha"]
    assert job.payload["timeout_s"] == 7.0


def test_shared_collector_command_receives_each_mockingbird_job_id(tmp_path):
    runner = tmp_path / "run.sh"
    runner.write_text("#!/bin/sh\nexit 0\n")
    runner.chmod(0o755)

    collector = tmp_path / "collect.sh"
    collector.write_text(
        "#!/bin/sh\n"
        "printf '{\"status\":\"FAIL\","
        "\"artifacts\":[\"artifact://%s\"]}\\n' \"$1\"\n"
    )
    collector.chmod(0o755)

    context = {
        "invocation_dir": str(tmp_path),
        "paths": {"adapter_workdir": str(tmp_path / "work" / "exec")},
        "execution": {
            "adapter": "command",
            "config": {
                "command": ["./run.sh"],
                "timeout_s": 5,
                "jobs": ["job-a"],
                "collect": {
                    "command": ["./collect.sh"],
                    "timeout_s": 5,
                },
            },
        },
    }

    adapter = Adapter()
    job = adapter.plan(context)[0]
    execution_context = _execution_context(tmp_path)
    execution = adapter.execute(context, job, execution_context)
    execution.paths = execution_context.evidence_paths()

    result = adapter.collect(context, [execution])[0]
    assert result.id == "job-a"
    assert result.status == "FAIL"
    assert result.artifacts == ["artifact://job-a"]


def test_probe_requires_finite_execution_timeout(tmp_path):
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)

    context = {
        "invocation_dir": str(tmp_path),
        "paths": {"adapter_workdir": str(tmp_path / "work" / "exec")},
        "execution": {
            "adapter": "command",
            "config": {
                "command": ["./run.sh"],
                "jobs": ["job-a"],
                "collect": {"mode": "exit-code"},
            },
        },
    }

    checks = Adapter().probe(context)

    assert any(
        item.status == "FAIL" and "execution.timeout_s is required" in item.message
        for item in checks
    )


def test_probe_reports_missing_project_command(tmp_path):
    context = {
        "invocation_dir": str(tmp_path),
        "paths": {"adapter_workdir": str(tmp_path / "work" / "exec")},
        "execution": {
            "adapter": "command",
            "config": {
                "command": ["./missing.sh"],
                "timeout_s": 5,
                "jobs": [],
                "collect": {"mode": "exit-code"},
            },
        },
    }

    checks = Adapter().probe(context)

    assert any(item.status == "FAIL" and "command not found" in item.message for item in checks)


def test_execution_timeout_returns_error_and_releases_local_process(tmp_path):
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\nsleep 10\n")
    script.chmod(0o755)

    context = {
        "invocation_dir": str(tmp_path),
        "paths": {"adapter_workdir": str(tmp_path / "work" / "exec")},
        "execution": {
            "adapter": "command",
            "config": {
                "command": ["./run.sh"],
                "timeout_s": 0.05,
                "jobs": ["job-a"],
                "collect": {"mode": "exit-code"},
            },
        },
    }

    adapter = Adapter()
    job = adapter.plan(context)[0]
    execution_context = _execution_context(tmp_path)
    execution = adapter.execute(context, job, execution_context)
    execution.paths = execution_context.evidence_paths()

    assert execution.observation["timed_out"] is True
    result = adapter.collect(context, [execution])[0]
    assert result.status == "ERROR"
