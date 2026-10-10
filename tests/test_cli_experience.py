"""Exercise the CLI as a new user, including copyable recovery instructions."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest
import yaml


@pytest.fixture
def session(tmp_path):
    definition = tmp_path / "jobs with spaces.yaml"
    definition.write_text(yaml.safe_dump({
        'plan': 'test',
        'execution': {'command': [sys.executable, '-c', 'pass'], 'timeout_s': 2, 'jobs': ['short', 'a_longer_job']},
        'scheduler': {'capacity_provider': 'fixed'},
    }))
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    def invoke(*args):
        return subprocess.run([sys.executable, "-m", "mockingbird.cli", *map(str, args)],
                              cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
    return definition, invoke


def test_first_run_recovery_and_human_outputs(session):
    definition, cli = session
    missing = cli("run", "test")
    assert missing.returncode == 1 and "Traceback" not in missing.stderr
    assert "not registered" in missing.stderr
    assert cli("prepare", definition).returncode == 0
    missing = cli("run", "test")
    commands = [shlex.split(line.strip())[1:] for line in missing.stderr.splitlines() if line.startswith("  mb ")]
    assert [cmd[0] for cmd in commands] == ["plan"]
    assert "\n\nRequired steps:" in missing.stderr
    for command in commands:
        completed = cli(*command)
        assert completed.returncode == 0, completed.stderr
        assert "Next: mb" in completed.stdout
        assert '"schema_version"' not in completed.stdout
    run = cli("run", "test")
    assert run.returncode == 0 and "Next: mb collect" in run.stdout
    assert "\n\n[2/2] a_longer_job: executing" in run.stdout
    assert "\n\nExecution finished:" in run.stdout
    assert "\n\nNext: mb collect" in run.stdout
    status = cli("status", "test")
    assert status.returncode == 0
    rows = [line for line in status.stdout.splitlines() if line.startswith(("JOB ", "short ", "a_longer_job "))]
    assert len(rows) == 3
    assert rows[0].index("EXECUTION") == rows[1].index("COMPLETE") == rows[2].index("COMPLETE")
    collected = cli("collect", "test")
    assert collected.returncode == 0 and "Result: PASS" in collected.stdout
    assert "Collection: 2/2 complete" in collected.stdout


def test_json_is_opt_in_and_parseable(session):
    definition, cli = session
    prepared = cli("prepare", definition, "--json")
    assert prepared.returncode == 0
    assert json.loads(prepared.stdout)["schema_version"] == 2
    for cycle in ("setup", "plan", "run"):
        assert cli(cycle, definition if cycle in {"prepare", "doctor", "all"} else "test").returncode == 0
    for cycle in ("status", "collect"):
        output = cli(cycle, "test", "--json")
        assert output.returncode == 0 and isinstance(json.loads(output.stdout), dict)
        if cycle == "status":
            assert all(job["execution"] == "RECORDED" for job in json.loads(output.stdout)["jobs"])


def test_missing_plan_does_not_repeat_successful_setup(session):
    definition, cli = session
    for cycle in ("prepare", "setup"):
        assert cli(cycle, definition if cycle in {"prepare", "doctor", "all"} else "test").returncode == 0
    output = cli("run", "test")
    assert output.returncode == 1
    assert "mb plan" in output.stderr and "mb setup" not in output.stderr


@pytest.mark.parametrize("kind", ["missing", "yaml", "root", "parallel", "selection", "run-dir"])
def test_user_errors_have_no_traceback(session, kind):
    definition, cli = session
    args = ["prepare", definition]
    if kind == "missing":
        args[1] = definition.with_name("not-found.yaml")
    elif kind == "yaml":
        definition.write_text("execution: [unterminated")
    elif kind == "root":
        definition.write_text("- not a mapping")
    elif kind == "parallel":
        data = yaml.safe_load(definition.read_text())
        data["scheduler"]["max_parallel"] = 2
        definition.write_text(yaml.safe_dump(data))
    else:
        for cycle in ("prepare", "setup", "plan"):
            assert cli(cycle, definition if cycle in {"prepare", "doctor", "all"} else "test").returncode == 0
        args = (["run", "test", "--test", "unknown"] if kind == "selection"
                else ["status", "test", "--run-dir", "missing-run"])
    output = cli(*args)
    assert output.returncode == 1 and "Error:" in output.stderr
    assert "Traceback" not in output.stderr


def test_debug_preserves_traceback(session):
    definition, cli = session
    for args in [("--debug", "run", "test"), ("run", "test", "--debug")]:
        output = cli(*args)
        assert output.returncode == 1 and "Traceback" in output.stderr


def test_stale_plan_recovery_after_reprepare(session):
    definition, cli = session
    for cycle in ("prepare", "setup", "plan", "prepare"):
        assert cli(cycle, definition if cycle in {"prepare", "doctor", "all"} else "test").returncode == 0
    output = cli("run", "test")
    assert output.returncode == 1 and "plan is stale" in output.stderr
    commands = [shlex.split(line.strip())[1:] for line in output.stderr.splitlines() if line.startswith("  mb ")]
    assert [cmd[0] for cmd in commands] == ["plan"]
    for command in commands:
        assert cli(*command).returncode == 0
    assert cli("run", "test").returncode == 0


def test_json_redirects_plugin_messages(monkeypatch, capsys):
    from mockingbird import cli
    monkeypatch.setattr(sys, "argv", ["mb", "prepare", "example.yaml", "--json"])
    monkeypatch.setattr(cli, "load_definition", lambda _: {})
    def prepare(_):
        print("plugin progress")
        return {"schema_version": 1}
    monkeypatch.setattr(cli, "prepare", prepare)
    cli.main()
    output = capsys.readouterr()
    assert json.loads(output.out) == {"schema_version": 1}
    assert "plugin progress" in output.err


def test_unexpected_error_has_debug_escape_hatch(monkeypatch, capsys):
    from mockingbird import cli
    monkeypatch.setattr(sys, "argv", ["mb", "run", "example"])
    def broken(_):
        raise KeyError("unexpected field")
    monkeypatch.setattr(cli, "plan_target", broken)
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "unexpected field" in output.err and "--debug" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("counts,status,complete", [
    ((1, 0, 0, 0, 2, 0, 0), "PENDING", False),
    ((1, 0, 0, 0, 0, 1, 1), "PENDING", False),
    ((2, 1, 0, 0, 0, 0, 0), "FAIL", True),
    ((0, 0, 1, 2, 0, 0, 0), "FAIL", True),
    ((3, 0, 0, 0, 0, 0, 0), "PASS", True),
])
def test_collection_summary_distinguishes_progress_from_verdict(counts, status, complete):
    from mockingbird.cli import _summary
    keys = ("pass", "fail", "error", "skip", "pending", "collection_error", "uncollected")
    summary = dict(zip(keys, counts), total=3)
    output = _summary({"summary": summary, "status": status, "collection_complete": complete})
    assert f"Collection: {3 if complete else 1}/3 complete" in output
    assert "Result:" not in output if not complete else f"Result: {status}" in output
    assert "PASS " + str(counts[0]) in output
    assert "collection error " + str(counts[5]) in output
