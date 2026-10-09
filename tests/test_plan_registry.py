"""A named plan remains the same plan after changing the caller's directory."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from mockingbird import registry


@pytest.fixture
def operator(tmp_path):
    project = tmp_path / "project with spaces"
    caller = tmp_path / "elsewhere"
    project.mkdir()
    caller.mkdir()
    definition = project / "smoke.yaml"
    data = {
        "plan": "smoke", "sources": [],
        "execution": {"command": [sys.executable, "-c", "import os; print(os.getcwd())"],
                      "args": [], "timeout_s": 5, "jobs": ["first"]},
        "scheduler": {"capacity_provider": "fixed"},
    }
    definition.write_text(json.dumps(data))
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))

    def cli(cwd, *args, expected=0):
        proc = subprocess.run([sys.executable, "-m", "mockingbird.cli", *map(str, args)],
                              cwd=cwd, env=env, capture_output=True, text=True, timeout=20)
        assert proc.returncode == expected, (args, proc.stdout, proc.stderr)
        assert "Traceback" not in proc.stderr
        return proc

    return project, caller, definition, data, cli


def test_named_workflow_after_cd_and_replan_preserves_run_history(operator):
    project, caller, definition, data, cli = operator
    cli(project, "prepare", definition)
    entry = registry.entry_path("smoke").read_bytes()
    cli(caller, "plan", "smoke")
    cli(caller, "setup", "smoke")
    cli(caller, "dry-run", "smoke")
    cli(caller, "run", "smoke")
    r1 = json.loads(cli(caller, "status", "smoke", "--json").stdout)
    run1 = Path(r1["run_dir"])
    assert run1.parent == project / "work/smoke/runs"
    stdout, = run1.glob("jobs/*/logs/stdout.log")
    assert stdout.read_text().strip() == str(project)
    assert r1["collection_counts"]["UNCOLLECTED"] == 1
    cli(caller, "collect", "smoke")
    old_plan = (run1 / "plan.json").read_bytes()
    old_result = (run1 / "result.json").read_bytes()

    # A different YAML in another directory still updates the same named plan.
    data["execution"]["jobs"] = ["first", "added"]
    edited = caller / "renamed.yaml"
    edited.write_text(json.dumps(data))
    cli(caller, "prepare", edited)
    cli(caller, "plan", "smoke")
    cli(caller, "run", "smoke")
    r2 = json.loads(cli(project / "work/smoke", "status", "smoke", "--json").stdout)
    assert r2["run_id"] != r1["run_id"] and r2["total"] == 2
    assert r2["collection_counts"]["UNCOLLECTED"] == 2
    assert (run1 / "plan.json").read_bytes() == old_plan
    assert (run1 / "result.json").read_bytes() == old_result
    definition.unlink()
    edited.unlink()
    cli(caller, "collect", "smoke", "--run", r1["run_id"])
    assert json.loads(cli(caller, "status", "smoke", "--json").stdout)["run_id"] == r2["run_id"]
    old = json.loads(cli(caller, "status", "smoke", "--run", r1["run_id"], "--plan").stdout)
    assert [job["id"] for job in old["jobs"]] == ["first"]
    rows = json.loads(cli(caller, "status", "smoke", "--history", "--json").stdout)["runs"]
    assert [row["run_id"] for row in rows] == [r2["run_id"], r1["run_id"]]
    assert rows[0]["result"] is None and rows[1]["result"] == "PASS"
    cli(caller, "collect", "smoke")
    assert registry.lookup("smoke")["definition_path"] == str(edited)
    assert not (caller / "work").exists()
    assert not (project / "work/smoke/work").exists()


def test_prepare_and_all_keep_the_original_cwd(operator):
    project, caller, definition, data, cli = operator
    cli(project, "prepare", definition)
    cli(caller, "prepare", definition)
    prepared = json.loads((project / "work/smoke/.reg/context.json").read_text())
    assert prepared["invocation_dir"] == str(project)
    cli(caller, "all", definition)
    result = json.loads(cli(caller, "status", "smoke", "--json").stdout)
    assert result["final"] == 1
    stdout, = Path(result["run_dir"]).glob("jobs/*/logs/stdout.log")
    assert stdout.read_text().strip() == str(project)
    assert not (caller / "work").exists()


def test_new_relative_source_uses_registered_project_during_reprepare(operator):
    project, caller, definition, data, cli = operator
    cli(project, "prepare", definition)
    local = project / "local-source"
    local.mkdir()
    def git(*args):
        return subprocess.run(["git", *args], cwd=local, check=True, capture_output=True, text=True)
    git("init")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (local / "payload").write_text("original project source")
    git("add", ".")
    git("commit", "-m", "source")
    data["sources"] = [{"name": "dut", "provider": "git", "url": "./local-source"}]
    definition.write_text(json.dumps(data))
    cli(caller, "doctor", definition)
    cli(caller, "prepare", definition)
    assert (project / "work/smoke/sources/dut/payload").read_text() == "original project source"
    assert not (caller / "work").exists()


def test_setup_capacity_and_collect_commands_use_saved_cwd(operator):
    project, caller, definition, data, cli = operator
    (project / "setup.py").write_text("from pathlib import Path; Path('setup-done').touch()")
    (project / "capacity.py").write_text("from pathlib import Path; Path('capacity-used').touch(); print(1)")
    (project / "collect.py").write_text("from pathlib import Path; Path('collect-used').touch(); print('{\"status\":\"PASS\"}')")
    data["setup"] = {"jobs": [{"id": "build", "command": [sys.executable, "setup.py"], "args": [], "timeout_s": 5}]}
    data["scheduler"] = {"capacity_provider": "command", "config": {"command": [sys.executable, "capacity.py"]}}
    data["execution"]["collect"] = {"command": [sys.executable, "collect.py"], "args": [], "timeout_s": 5}
    definition.write_text(json.dumps(data))
    cli(project, "prepare", definition)
    cli(caller, "setup", "smoke")
    cli(caller, "plan", "smoke")
    cli(caller, "run", "smoke")
    cli(caller, "collect", "smoke")
    assert all((project / n).is_file() for n in ["setup-done", "capacity-used", "collect-used"])
    assert not list(caller.iterdir())


def test_legacy_confirmation_registers_without_repeating_prepare(operator):
    project, caller, definition, _, cli = operator
    cli(project, "all", definition)
    context = project / "work/smoke/.reg/context.json"
    original_context = context.read_bytes()
    registry.entry_path("smoke").unlink()
    missing = cli(caller, "status", "smoke", "--history", expected=1)
    assert "not registered" in missing.stderr and "original project directory" in missing.stderr
    assert "No runs yet" not in missing.stdout
    cli(project, "prepare", definition)
    cli(project, "plan", "smoke")
    assert context.read_bytes() != original_context
    assert json.loads(cli(caller, "status", "smoke", "--json").stdout)["final"] == 1


def test_unknown_name_does_not_create_storage(operator):
    project, caller, _, _, cli = operator
    for args in [("status", "typo"), ("status", "typo", "--history"), ("run", "typo")]:
        response = cli(caller, *args, expected=1)
        assert "not registered" in response.stderr
        assert "No runs yet" not in response.stdout
    assert not registry.entry_path("typo").parent.exists()
    assert not (caller / "work").exists()


def test_missing_registered_location_is_not_replaced_by_local_copy(operator):
    project, caller, definition, _, cli = operator
    cli(project, "all", definition)
    shutil.copytree(project / "work", caller / "work")
    shutil.rmtree(project / "work")
    entry = registry.entry_path("smoke").read_bytes()
    response = cli(caller, "status", "smoke", "--history", expected=1)
    assert "unavailable" in response.stderr and str(project / "work/smoke") in response.stderr
    assert registry.entry_path("smoke").read_bytes() == entry


def test_two_legacy_locations_with_same_name_are_not_silently_merged(operator):
    project, caller, definition, _, cli = operator
    cli(project, "all", definition)
    shutil.copytree(project / "work", caller / "work")
    before = (project / "work/smoke/.reg/context.json").read_bytes()
    for command in ["prepare", "all"]:
        response = cli(caller, command, definition, expected=1)
        assert "another local environment" in response.stderr
    assert (project / "work/smoke/.reg/context.json").read_bytes() == before


def test_explicit_external_run_does_not_require_or_change_registration(operator):
    project, caller, definition, _, cli = operator
    cli(project, "all", definition)
    run_dir, = (project / "work/smoke/runs").iterdir()
    registry.entry_path("smoke").unlink()
    cli(caller, "status", "smoke", "--run-dir", run_dir)
    cli(caller, "collect", "smoke", "--run-dir", run_dir)
    cli(caller, "status", "smoke", "--run-dir", run_dir, "--plan")
    assert not registry.entry_path("smoke").exists()
    cli(caller, "status", "different", "--run-dir", run_dir, expected=1)


def test_relative_registry_override_is_rejected(monkeypatch):
    monkeypatch.setenv("MB_STATE_DIR", "relative/path")
    with pytest.raises(ValueError, match="absolute path"):
        registry.lookup("smoke")


def test_corrupt_registry_has_actionable_error(operator):
    project, caller, definition, _, cli = operator
    cli(project, "prepare", definition)
    path = registry.entry_path("smoke")
    path.write_text("[]")
    response = cli(caller, "status", "smoke", expected=1)
    assert "invalid plan registration" in response.stderr and str(path) in response.stderr


def test_failed_prepare_reserves_name_and_retries_at_original_location(tmp_path, monkeypatch):
    from mockingbird.context import prepare, load_definition, plan_target
    project = tmp_path / "project"
    caller = tmp_path / "caller"
    project.mkdir(); caller.mkdir()
    definition = project / "plan.yaml"
    definition.write_text(json.dumps({"plan": "smoke", "sources": [{"name": "dut", "provider": "fake", "url": "fake"}],
                                      "execution": {"command": ["true"], "timeout_s": 5, "jobs": ["a"]},
                                      "scheduler": {"capacity_provider": "fixed"}}))
    class Provider:
        fail = True
        def materialize(self, source, destination):
            assert source['_invocation_dir'] == str(project)
            if self.fail:
                raise RuntimeError("acquisition interrupted")
            destination.mkdir(parents=True, exist_ok=True)
            return {"resolved_revision": "test"}
    provider = Provider()
    monkeypatch.setattr("mockingbird.context.load_source_provider", lambda _: provider)
    monkeypatch.chdir(project)
    with pytest.raises(RuntimeError, match="acquisition interrupted"):
        prepare(load_definition(definition))
    assert registry.lookup("smoke")["directory"] == str(project)
    provider.fail = False
    monkeypatch.chdir(caller)
    prepare(load_definition(definition))
    assert plan_target("smoke")["_invocation_dir"] == str(project)
    assert not (caller / "work").exists()


def test_first_prepare_name_reservation_prevents_two_locations(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    first = tmp_path / "one"; first.mkdir()
    second = tmp_path / "two"; second.mkdir()
    def definition(root):
        return {"plan": "smoke", "_invocation_dir": str(root), "_definition_path": str(root / "jobs.yaml")}
    with registry.registration(definition(first)):
        with ThreadPoolExecutor(max_workers=1) as pool:
            def conflicting():
                with registry.registration(definition(second)):
                    pytest.fail("another registration must not run concurrently")
            with pytest.raises(RuntimeError, match="registration is busy"):
                pool.submit(conflicting).result(timeout=5)
    assert registry.lookup("smoke")["directory"] == str(first)


def test_plan_path_lifecycle_and_failed_confirmation(operator):
    project, caller, old, data, cli = operator
    (project / 'plan').mkdir()
    path = project / 'plan/xxx.yml'
    old.rename(path)
    cli(project, 'prepare', 'plan/xxx.yml')
    cli(caller, 'setup', 'smoke')
    cli(caller, 'plan', 'smoke')
    saved = project / 'work/smoke/.reg/plan.json'
    before = saved.read_bytes()
    cli(project, 'plan', 'plan/xxx.yml', expected=1)
    data['plan'] = 'wrong'
    path.write_text(json.dumps(data))
    assert 'must contain plan: smoke' in cli(caller, 'plan', 'smoke', expected=1).stderr
    assert saved.read_bytes() == before
    path.unlink()
    cli(caller, 'plan', 'smoke', expected=1)
    assert saved.read_bytes() == before
    cli(caller, 'run', 'smoke')
    cli(caller, 'collect', 'smoke')


def test_git_run_observations_and_reprepare(operator):
    project, caller, definition, data, cli = operator
    origin = project / 'origin'; origin.mkdir()
    def git(root, *args):
        return subprocess.run(['git', '-C', str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git(origin, 'init')
    git(origin, 'config', 'user.email', 'test@example.invalid')
    git(origin, 'config', 'user.name', 'Test')
    (origin / 'tracked').write_text('original')
    (origin / '.gitignore').write_text('ignored\n')
    git(origin, 'add', '.')
    git(origin, 'commit', '-m', 'initial')
    first = git(origin, 'rev-parse', 'HEAD')
    data['sources'] = [{'name': 'dut', 'provider': 'git', 'url': str(origin)}]
    definition.write_text(json.dumps(data))
    cli(project, 'prepare', definition)
    tree = project / 'work/smoke/sources/dut'
    cli(caller, 'plan', 'smoke')
    records = []
    def run():
        output = cli(caller, 'run', 'smoke').stdout
        status = json.loads(cli(caller, 'status', 'smoke', '--json').stdout)
        path = Path(status['run_dir']) / 'run.json'
        records.append((path, path.read_bytes()))
        obs = json.loads(path.read_text())['source_observations']['dut']
        assert 'Checking sources...' in output
        assert 'Sources: 1 checked,' in output
        return obs
    (tree / 'ignored').touch()
    assert run() == dict(prepared_commit=first, current_commit=first, tracked_dirty=False)
    (tree / 'untracked').touch()
    assert run()['tracked_dirty'] is False
    (tree / 'untracked').unlink()
    (tree / 'tracked').write_text('edited')
    assert run()['tracked_dirty'] is True
    cli(caller, 'prepare', definition)
    cli(caller, 'plan', 'smoke')
    assert run() == dict(prepared_commit=first, current_commit=first, tracked_dirty=True)
    git(tree, 'add', 'tracked')
    assert run()['tracked_dirty'] is True
    git(tree, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'edit')
    second = git(tree, 'rev-parse', 'HEAD')
    assert run() == dict(prepared_commit=first, current_commit=second, tracked_dirty=False)
    cli(caller, 'prepare', definition)
    cli(caller, 'plan', 'smoke')
    assert run() == dict(prepared_commit=second, current_commit=second, tracked_dirty=False)
    shutil.rmtree(tree)
    failed_observation = run()
    assert failed_observation['tracked_dirty'] is None and 'error' in failed_observation
    output = cli(caller, 'run', 'smoke', '--skip-source-check').stdout
    assert 'Sources: skipped (--skip-source-check)' in output
    assert 'Checking sources' not in output
    exported = cli(caller, 'save', 'smoke', '--as', 'repro', '--output', caller / 'repro.yml')
    assert 'run-time HEAD unknown' in exported.stderr
    assert 'clean/dirty state unknown' in exported.stderr
    assert all(path.read_bytes() == contents for path, contents in records)


@pytest.mark.parametrize('command', ['run', 'all'])
def test_skip_source_check_cli(operator, command):
    project, caller, definition, data, cli = operator
    if command == 'run':
        cli(project, 'prepare', definition)
        cli(caller, 'plan', 'smoke')
    target = 'smoke' if command == 'run' else definition
    output = cli(caller, command, target, '--skip-source-check').stdout
    assert 'Sources: skipped (--skip-source-check)' in output
    assert 'Checking sources' not in output
    state = json.loads(cli(caller, 'status', 'smoke', '--json').stdout)
    record = json.loads((Path(state['run_dir']) / 'run.json').read_text())
    assert record['source_check_skipped'] is True
    assert record['source_observations'] == {}
    assert record['status'] == 'EXECUTED'
    cli(caller, 'collect', 'smoke')
