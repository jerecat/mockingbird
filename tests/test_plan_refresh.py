"""Edit -> plan -> run, and explicit interactive recovery for forgotten plan."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from mockingbird import cli, lifecycle
from mockingbird.context import load_definition, prepare, load_state, metadata_path
from mockingbird.errors import PlanChangedError, PrerequisiteError
from mockingbird.io import read_json, write_json
from test_review_regressions import definition, ready


def test_refresh_keeps_prepared_context_sources_and_setup(tmp_path, monkeypatch):
    d = definition(tmp_path)
    d["setup"] = {"jobs": [{"id": "setup", "command": [sys.executable, "-c", "pass"], "args": [], "timeout_s": 2}]}
    ready(d)
    context_file = metadata_path(d) / "context.json"
    before = context_file.read_bytes()
    state = load_state(d)
    monkeypatch.setattr("mockingbird.context.load_source_provider",
                        lambda *_: pytest.fail("plan must not acquire sources"))
    d["execution"]["command"] = [sys.executable, "-c", "print('new')"]
    d["execution"]["args_suffix"] = ["suffix"]
    with pytest.raises(PlanChangedError):
        lifecycle.run(d)
    assert not list((tmp_path / "runs").iterdir())
    lifecycle.create_plan(d)
    assert context_file.read_bytes() == before
    assert load_state(d)["last_setup_dir"] == state["last_setup_dir"]
    executions, rd, _ = lifecycle.run(d)
    assert all(e.observation["returncode"] == 0 for e in executions)
    assert read_json(rd / "context.json")["execution"]["config"]["args_suffix"] == ["suffix"]
    assert lifecycle.collect(d, rd)[0]["status"] == "PASS"


@pytest.mark.parametrize("field,value", [
    ("sources", [{"name": "new", "provider": "git", "url": "unused"}]),
    ("setup", {"jobs": [{"id": "a", "command": ["echo"], "timeout_s": 2}]}),
    ("scheduler", {"capacity_provider": "fixed", "config": {"slots": 0}}),
    ("run_root", "elsewhere"),
    ("name", "changed"),
    ("execution", {"adapter": "demo_linux", "config": {}}),
])
def test_preparation_changes_never_auto_replan(tmp_path, field, value):
    d = definition(tmp_path)
    ready(d)
    d[field] = value
    for action in (lifecycle.create_plan, lifecycle.run, lifecycle.setup):
        with pytest.raises(PrerequisiteError) as exc:
            action(d)
        assert exc.value.steps[0] == "prepare"
    assert not list((tmp_path / "runs").iterdir())


def test_script_changes_do_not_require_plan(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("print('old')")
    d = definition(tmp_path)
    d["execution"]["command"] = [sys.executable, str(script)]
    ready(d)
    script.write_text("print('new')")
    executions, rd, _ = lifecycle.run(d)
    assert all(Path(e.observation["execution_context"]["stdout_path"]).read_text().strip() == "new"
               for e in executions)


def test_invalid_updated_plan_cannot_execute_old_jobs(tmp_path):
    d = definition(tmp_path)
    ready(d)
    d["execution"]["args"] = "not an argv list"
    with pytest.raises(ValueError, match="args"):
        lifecycle.create_plan(d)
    assert not (metadata_path(d) / "plan.json").exists()
    with pytest.raises(PrerequisiteError):
        lifecycle.run(d)
    assert not list((tmp_path / "runs").iterdir())


def test_legacy_context_and_plan_can_refresh(tmp_path):
    d = definition(tmp_path)
    ready(d)
    for filename, key in [("context.json", "preparation_contract"), ("plan.json", "execution")]:
        path = metadata_path(d) / filename
        data = read_json(path)
        del data[key]
        write_json(path, data)
    lifecycle.load_plan(d)
    d["execution"]["jobs"] = ["new"]
    with pytest.raises(PlanChangedError):
        lifecycle.run(d)
    lifecycle.create_plan(d)
    assert [j.id for j in lifecycle.plan_jobs(d)] == ["new"]


def test_bool_is_not_equal_to_numeric_timeout(tmp_path):
    d = definition(tmp_path)
    d["execution"]["timeout_s"] = 1
    ready(d)
    d["execution"]["timeout_s"] = True
    with pytest.raises(PlanChangedError):
        lifecycle.run(d)
    with pytest.raises(ValueError):
        lifecycle.create_plan(d)


class Terminal(io.StringIO):
    def isatty(self):
        return True


@pytest.mark.parametrize("answer,run_expected", [("\n", True), ("y\n", True), ("n\n", False),
                                                ("", False), ("oops\nn\n", False)])
def test_cli_update_confirmation(tmp_path, monkeypatch, capsys, answer, run_expected):
    d = definition(tmp_path)
    path = Path(d["_definition_path"])
    path.write_text(json.dumps({k: v for k, v in d.items() if not k.startswith("_")}))
    ready(load_definition(path))
    data = json.loads(path.read_text())
    data["execution"]["jobs"] = ["new"]
    path.write_text(json.dumps(data))
    monkeypatch.setattr(sys, "stdin", Terminal(answer))
    parser = cli.build_parser()
    cli._dispatch(parser.parse_args(["run", str(path)]), parser)
    out = capsys.readouterr().out
    assert "Update the plan and run? [Y/n]" in out
    runs = list((tmp_path / "runs").iterdir())
    assert bool(runs) == run_expected
    if run_expected:
        assert list(read_json(runs[0] / "run.json")["jobs"]) == ["new"]
    else:
        assert "cancelled" in out


def test_noninteractive_cli_rejects_changed_plan_even_with_yes_input(tmp_path):
    d = definition(tmp_path)
    path = Path(d["_definition_path"])
    path.write_text(json.dumps({k: v for k, v in d.items() if not k.startswith("_")}))
    ready(load_definition(path))
    data = json.loads(path.read_text())
    data["execution"]["jobs"] = ["new"]
    path.write_text(json.dumps(data))
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run([sys.executable, "-m", "mockingbird.cli", "run", str(path)],
                            env=env, input="y\n", capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert "mb plan" in result.stderr
    assert "Update the plan and run?" not in result.stdout
    assert not list((tmp_path / "runs").iterdir())


def test_old_run_collect_uses_its_own_contract_after_edit(tmp_path):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    d["execution"]["collect"] = {"command": ["missing"], "timeout_s": 2}
    assert lifecycle.collect(d, rd)[0]["status"] == "PASS"


def test_accepted_invalid_plan_never_starts_run(tmp_path, monkeypatch):
    d = definition(tmp_path)
    path = Path(d["_definition_path"])
    path.write_text(json.dumps({k: v for k, v in d.items() if not k.startswith("_")}))
    ready(load_definition(path))
    data = json.loads(path.read_text())
    data["execution"]["args"] = "bad"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(sys, "stdin", Terminal("\n"))
    parser = cli.build_parser()
    with pytest.raises(ValueError, match="args"):
        cli._dispatch(parser.parse_args(["run", str(path)]), parser)
    assert not list((tmp_path / "runs").iterdir())


def test_prompt_interrupt_never_starts_run(tmp_path, monkeypatch):
    d = definition(tmp_path)
    path = Path(d["_definition_path"])
    path.write_text(json.dumps({k: v for k, v in d.items() if not k.startswith("_")}))
    ready(load_definition(path))
    data = json.loads(path.read_text())
    data["execution"]["jobs"] = ["changed"]
    path.write_text(json.dumps(data))
    monkeypatch.setattr(sys, "stdin", Terminal())
    def interrupt(*args):
        raise KeyboardInterrupt()
    monkeypatch.setattr("builtins.input", interrupt)
    parser = cli.build_parser()
    with pytest.raises(KeyboardInterrupt):
        cli._dispatch(parser.parse_args(["run", str(path)]), parser)
    assert not list((tmp_path / "runs").iterdir())


def test_launch_error_shows_reason_and_record_path(tmp_path, capsys):
    d = definition(tmp_path)
    d["execution"]["command"] = [str(tmp_path / "missing executable")]
    d["execution"]["jobs"] = ["job"]
    ready(d)
    executions, rd, _ = lifecycle.run(d, on_progress=cli._progress)
    out = capsys.readouterr().out
    assert "FileNotFoundError" in out
    assert "execution.json" in out and "stderr.log" in out
    assert executions[0].observation["launch_error"]
