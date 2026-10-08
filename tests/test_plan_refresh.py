"""Explicit confirmation owns the next execution; runs retain their own plan."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from mockingbird import cli, lifecycle, status
from mockingbird.context import load_definition, prepare, load_state, metadata_path, plan_target
from mockingbird.errors import PrerequisiteError
from mockingbird.io import read_json, write_json
from test_review_regressions import definition, ready


def test_refresh_keeps_prepared_context_sources_and_setup(tmp_path, monkeypatch):
    d = definition(tmp_path)
    d['setup'] = {'jobs': [{'id': 'setup', 'command': [sys.executable, '-c', 'pass'],
                          'args': [], 'timeout_s': 2}]}
    ready(d)
    before = (metadata_path(d) / 'context.json').read_bytes()
    state = load_state(d)
    monkeypatch.setattr('mockingbird.context.load_source_provider',
                        lambda *_: pytest.fail('plan must not acquire sources'))
    d['execution']['command'] = [sys.executable, '-c', "print('new')"]
    d['execution']['args_suffix'] = ['suffix']
    # Editing alone has no effect, including when using the Python API.
    _, old, _ = lifecycle.run(d)
    assert read_json(old / 'plan.json')['context']['execution']['config']['command'][-1] == 'pass'
    lifecycle.create_plan(d)
    assert (metadata_path(d) / 'context.json').read_bytes() == before
    assert load_state(d)['last_setup_dir'] == state['last_setup_dir']
    executions, rd, _ = lifecycle.run(plan_target('A', tmp_path))
    assert all(e.observation['returncode'] == 0 for e in executions)
    assert read_json(rd / 'plan.json')['context']['execution']['config']['args_suffix'] == ['suffix']
    assert lifecycle.collect(d, rd)[0]['status'] == 'PASS'


@pytest.mark.parametrize('field,value', [
    ('sources', [{'name': 'new', 'provider': 'git', 'url': 'unused'}]),
    ('setup', {'jobs': [{'id': 'a', 'command': ['echo'], 'timeout_s': 2}]}),
    ('execution', {'adapter': 'demo_linux', 'config': {}}),
])
def test_preparation_changes_require_explicit_prepare_at_confirmation(tmp_path, field, value):
    d = definition(tmp_path)
    ready(d)
    before = (metadata_path(d) / 'plan.json').read_bytes()
    d[field] = value
    with pytest.raises(PrerequisiteError) as exc:
        lifecycle.create_plan(d)
    assert exc.value.steps[0] == 'prepare'
    assert (metadata_path(d) / 'plan.json').read_bytes() == before
    lifecycle.run(d)  # The last confirmed plan still applies.


def test_invalid_confirmation_keeps_last_successful_plan(tmp_path):
    d = definition(tmp_path)
    ready(d)
    before = (metadata_path(d) / 'plan.json').read_bytes()
    d['execution']['args'] = 'not an argv list'
    with pytest.raises(ValueError, match='args'):
        lifecycle.create_plan(d)
    assert (metadata_path(d) / 'plan.json').read_bytes() == before
    executions, _, _ = lifecycle.run(d)
    assert [e.job_id for e in executions] == ['a', 'b']


def test_non_json_meta_cannot_replace_plan(tmp_path):
    d = definition(tmp_path)
    ready(d)
    before = (metadata_path(d) / 'plan.json').read_bytes()
    d['meta'] = {'not-json': {1, 2}}
    with pytest.raises(TypeError):
        lifecycle.create_plan(d)
    assert (metadata_path(d) / 'plan.json').read_bytes() == before


def test_saved_plan_contains_context_definition_and_project_meta(tmp_path):
    d = definition(tmp_path)
    d['meta'] = {'toolchain': 'example-compiler-1', 'seed': 123}
    ready(d)
    plan = lifecycle.load_plan(d)
    assert plan['meta'] == d['meta']
    assert plan['definition']['plan'] == 'A'
    assert '_definition_path' not in plan['definition']
    assert plan['context']['invocation_dir'] == str(tmp_path)
    assert plan['context']['orchestrator']['version']
    # Changing current preparation data cannot supply a different scheduler.
    saved = read_json(metadata_path(d) / 'context.json')
    saved['scheduler']['config'] = {'slots': 0}
    write_json(metadata_path(d) / 'context.json', saved)
    _, run_dir, _ = lifecycle.run(d)
    assert read_json(run_dir / 'plan.json') == plan


def test_same_name_across_yaml_files_and_yaml_deletion(tmp_path):
    d = definition(tmp_path)
    a = tmp_path / 'a.yaml'
    b = tmp_path / 'elsewhere' / 'b.yaml'
    b.parent.mkdir()
    a.write_text(json.dumps({k: v for k, v in d.items() if not k.startswith('_')}))
    data = json.loads(a.read_text())
    data['execution']['jobs'] = ['from-b']
    b.write_text(json.dumps(data))
    # Both definitions are loaded from the same invocation directory.
    old_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        ready(load_definition(a))
        first, rd1, _ = lifecycle.run(plan_target('A'))
        lifecycle.create_plan(load_definition(b))
        a.unlink()
        b.unlink()
        second, rd2, _ = lifecycle.run(plan_target('A'))
        assert [e.job_id for e in first] == ['a', 'b']
        assert [e.job_id for e in second] == ['from-b']
        assert status.snapshot(plan_target('A'), rd1)['total'] == 2
        assert lifecycle.collect(plan_target('A'), rd1)[0]['collection_complete']
        assert status.plan_details(plan_target('A'), rd1)['definition']['execution']['jobs'] == ['a', 'b']
        assert [r['run_id'] for r in status.history(plan_target('A'))['runs']] == [rd2.name, rd1.name]
    finally:
        os.chdir(old_cwd)


def test_new_name_has_independent_history(tmp_path):
    a, b = definition(tmp_path), definition(tmp_path, 'B')
    ready(a)
    _, first, _ = lifecycle.run(a)
    ready(b)
    _, second, _ = lifecycle.run(b)
    assert first.parent != second.parent
    assert [r['run_id'] for r in status.history(a)['runs']] == [first.name]
    with pytest.raises(ValueError, match='different plan'):
        status.snapshot(b, first)


def test_replan_during_run_and_latest_started_survives_out_of_order_finish(tmp_path, monkeypatch):
    d = definition(tmp_path)
    ready(d)
    adapter = lifecycle.load_adapter('command')
    original = adapter.execute
    entered, release = threading.Event(), threading.Event()
    failures = []
    first_result = []
    def execute(context, job, execution):
        if job.id == 'a':
            entered.set()
            assert release.wait(10)
        return original(context, job, execution)
    monkeypatch.setattr(adapter, 'execute', execute)
    monkeypatch.setattr(lifecycle, 'load_adapter', lambda _: adapter)
    def first():
        try:
            first_result.append(lifecycle.run(d))
        except BaseException as exc:
            failures.append(exc)
    thread = threading.Thread(target=first)
    thread.start()
    try:
        assert entered.wait(10)
        with pytest.raises(RuntimeError, match='busy'):
            prepare(d)
        with pytest.raises(RuntimeError, match='busy'):
            lifecycle.setup(d)
        d['execution']['jobs'] = ['next']
        lifecycle.create_plan(d)
        second, rd2, _ = lifecycle.run(d)
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and not failures
    first, rd1, _ = first_result[0]
    assert [e.job_id for e in first] == ['a', 'b']
    assert [e.job_id for e in second] == ['next']
    assert read_json(rd1 / 'plan.json')['jobs'][0]['id'] == 'a'
    assert status.snapshot(d)['run_id'] == rd2.name
    lifecycle.collect(d, rd1)
    assert status.snapshot(d)['run_id'] == rd2.name


def test_old_run_collect_uses_its_own_contract_after_edit(tmp_path):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    d['execution']['collect'] = {'command': ['missing'], 'timeout_s': 2}
    lifecycle.create_plan(d)
    assert lifecycle.collect(d, rd)[0]['status'] == 'PASS'


def test_scheduler_change_is_adopted_only_by_plan(tmp_path):
    d = definition(tmp_path)
    ready(d)
    d['scheduler']['poll_interval_s'] = .02
    assert lifecycle.load_plan(d)['context']['scheduler']['poll_interval_s'] == .01
    lifecycle.create_plan(d)
    assert lifecycle.load_plan(d)['context']['scheduler']['poll_interval_s'] == .02


def test_cli_named_commands_do_not_read_yaml_or_prompt_for_updates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = definition(tmp_path)
    path = Path(d['_definition_path'])
    path.write_text(json.dumps({k: v for k, v in d.items() if not k.startswith('_')}))
    ready(load_definition(path))
    path.write_text('this is no longer valid YAML: [')
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    for args in [('run', 'A'), ('status', 'A', '--history', '--json'), ('status', 'A', '--plan', '--json')]:
        result = subprocess.run([sys.executable, '-m', 'mockingbird.cli', *args], cwd=tmp_path,
                                env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert 'Update the plan' not in result.stdout
        if '--json' in args:
            assert json.loads(result.stdout)['plan'] == 'A'


def test_launch_error_shows_reason_and_record_path(tmp_path, capsys):
    d = definition(tmp_path)
    d['execution']['command'] = [str(tmp_path / 'missing executable')]
    d['execution']['jobs'] = ['job']
    ready(d)
    lifecycle.run(d, on_progress=cli._progress)
    out = capsys.readouterr().out
    assert 'FileNotFoundError' in out
    assert 'execution.json' in out and 'stderr.log' in out


@pytest.mark.parametrize('name', ['', '.', '..', '../other', '/absolute', 'a/b', 'a\\b', 'a b', '-option', 'a\n', 'x' * 129, None, 1])
def test_plan_names_cannot_alias_or_escape_storage(tmp_path, name):
    d = definition(tmp_path)
    d['plan'] = name
    with pytest.raises(ValueError, match='plan must'):
        prepare(d)
    assert not (tmp_path / 'work').exists()


@pytest.mark.parametrize('removed', ['name', 'workspace', 'run_root'])
def test_removed_yaml_keys_have_migration_guidance(tmp_path, removed):
    d = definition(tmp_path)
    d[removed] = 'old'
    with pytest.raises(ValueError, match="use 'plan:"):
        prepare(d)
    assert not (tmp_path / 'work').exists()


def test_old_schema_two_run_can_be_inspected_and_collected_without_yaml(tmp_path):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    plan = read_json(rd / 'plan.json')
    old_context = plan.pop('context')
    old_context['name'] = old_context.pop('plan')
    plan['schema_version'] = 2
    plan.pop('plan')
    write_json(rd / 'plan.json', plan)
    write_json(rd / 'context.json', old_context)
    record = read_json(rd / 'run.json')
    record['schema_version'] = 2
    record['name'] = record.pop('plan')
    write_json(rd / 'run.json', record)
    target = plan_target('A', tmp_path / 'different-location')
    assert status.snapshot(target, rd)['total'] == 2
    assert lifecycle.collect(target, rd)[0]['status'] == 'PASS'


def test_named_cli_run_id_history_and_historical_plan(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    d = definition(tmp_path)
    ready(d)
    _, first, _ = lifecycle.run(d)
    d['execution']['jobs'] = ['new']
    lifecycle.create_plan(d)
    _, second, _ = lifecycle.run(d)
    parser = cli.build_parser()
    cli._dispatch(parser.parse_args(['collect', 'A', '--run', first.name]), parser)
    capsys.readouterr()
    cli._dispatch(parser.parse_args(['status', 'A', '--run', first.name, '--plan']), parser)
    assert [j['id'] for j in json.loads(capsys.readouterr().out)['jobs']] == ['a', 'b']
    cli._dispatch(parser.parse_args(['status', 'A', '--history', '--json']), parser)
    rows = json.loads(capsys.readouterr().out)['runs']
    assert [r['run_id'] for r in rows] == [second.name, first.name]
    assert rows[1]['result'] == 'PASS' and rows[0]['result'] is None
    with pytest.raises(ValueError, match='run ID'):
        cli._dispatch(parser.parse_args(['status', 'A', '--run', '../other']), parser)


def test_move_of_whole_environment_requires_explicit_prepare(tmp_path):
    import shutil
    d = definition(tmp_path)
    ready(d)
    other = tmp_path / 'other'
    shutil.copytree(tmp_path / 'work', other / 'work')
    with pytest.raises(PrerequisiteError, match='moved'):
        lifecycle.run(plan_target('A', other))


def test_atomic_confirmation_failure_preserves_previous_file(tmp_path, monkeypatch):
    d = definition(tmp_path)
    ready(d)
    before = (metadata_path(d) / 'plan.json').read_bytes()
    d['execution']['jobs'] = ['new']
    def failed_publish(*_):
        raise OSError('publication interrupted')
    with monkeypatch.context() as patch:
        patch.setattr('mockingbird.io.os.replace', failed_publish)
        with pytest.raises(OSError, match='publication interrupted'):
            lifecycle.create_plan(d)
    assert (metadata_path(d) / 'plan.json').read_bytes() == before
    assert [j.id for j in lifecycle.plan_jobs(d)] == ['a', 'b']


def test_interactive_confirmation_executes_the_displayed_plan_and_selection(tmp_path, monkeypatch, capsys):
    from mockingbird.selection import Selection
    d = definition(tmp_path)
    ready(d)
    selected = tmp_path / 'selected.txt'
    selected.write_text('a\n')
    def confirm(context, jobs, selection):
        assert [job.id for job in jobs] == ['a']
        d['execution']['jobs'] = ['next']
        lifecycle.create_plan(d)
        selected.write_text('next\n')
        return True
    executions, run_dir, _ = lifecycle.run(d, Selection(selection_file=str(selected)), confirm=confirm)
    assert [e.job_id for e in executions] == ['a']
    assert read_json(run_dir / 'run.json')['selection']['selected_ids'] == ['a']
    assert [j.id for j in lifecycle.plan_jobs(d)] == ['next']


def test_cancelled_confirmation_creates_no_run(tmp_path):
    d = definition(tmp_path)
    ready(d)
    assert lifecycle.run(d, confirm=lambda *_: False) is None
    assert not list((tmp_path / 'work/A/runs').iterdir())
    assert not (metadata_path(d) / 'last_run.json').exists()


def test_selection_export_error_reports_successful_confirmation(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    d = definition(tmp_path)
    path = Path(d['_definition_path'])
    path.write_text(json.dumps({k: v for k, v in d.items() if not k.startswith('_')}))
    prepare(d)
    directory = tmp_path / 'directory'; directory.mkdir()
    monkeypatch.setattr(sys, 'argv', ['mb', 'plan', 'A', '--write-selection', str(directory)])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert 'Plan was confirmed' in capsys.readouterr().err
    assert [j.id for j in lifecycle.plan_jobs(d)] == ['a', 'b']
