"""Export historical contracts and replay in an independent operator workspace."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from test_plan_registry import operator
from mockingbird import registry
from mockingbird.save import save_plan
from mockingbird.context import plan_target


def test_save_selected_historical_run_and_receiver(operator):
    project, caller, definition, data, cli = operator
    origin = project / 'origin'; origin.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(origin), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init'); git('config', 'user.name', 'Test'); git('config', 'user.email', 'test@example.invalid')
    (origin / 'payload').write_text('original')
    git('add', '.'); git('commit', '-m', 'original')
    commit = git('rev-parse', 'HEAD')
    data['sources'] = [{'name': 'rtl', 'provider': 'git', 'url': str(origin)}]
    data['execution']['jobs'] = ['first', 'second', 'not-selected']
    data['setup'] = {'jobs': [{'id': 'build', 'command': [sys.executable, '-c', 'print("build")'],
                            'args': [], 'timeout_s': 5}]}
    definition.write_text(json.dumps(data))
    cli(project, 'all', definition, '--test', 'first', '--test', 'second')
    status = json.loads(cli(caller, 'status', 'smoke', '--json').stdout)
    run = Path(status['run_dir'])
    before = {p: p.read_bytes() for p in run.rglob('*') if p.is_file()}
    data['execution']['jobs'] = ['new']
    definition.write_text(json.dumps(data))
    cli(caller, 'plan', 'smoke'); cli(caller, 'run', 'smoke')
    definition.unlink()
    output = caller / 'repro.yml'
    response = cli(caller, 'save', 'smoke', '--run', run.name, '--as', 'repro', '--output', output)
    assert 'Jobs: 2' in response.stdout
    saved = yaml.safe_load(output.read_text())
    assert saved['plan'] == 'repro'
    assert [j['id'] for j in saved['execution']['jobs']] == ['first', 'second']
    assert saved['sources'][0]['revision'] == commit
    assert saved['setup'] == data['setup']
    assert registry.lookup('repro') is None
    assert not (caller / 'work').exists()
    assert all(p.read_bytes() == value for p, value in before.items())
    assert cli(caller, 'save', 'smoke', '--as', 'repro', '--output', output, expected=1)
    one = caller / 'one.yml'
    cli(caller, 'save', 'smoke', '--run', run.name, '--test', 'second', '--as', 'one', '--output', one)
    assert [j['id'] for j in yaml.safe_load(one.read_text())['execution']['jobs']] == ['second']
    # Another operator starts with unrelated sources and an independent registry.
    receiver = caller / 'receiver'; receiver.mkdir()
    unrelated = receiver / 'work/other/sources/rtl'; unrelated.mkdir(parents=True)
    (unrelated / 'keep').write_text('untouched')
    env = dict(os.environ, MB_STATE_DIR=str(receiver / 'state'),
               PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    for command, argument in [('prepare', str(output)), ('setup', 'repro'), ('plan', 'repro'),
                              ('run', 'repro'), ('collect', 'repro')]:
        result = subprocess.run([sys.executable, '-m', 'mockingbird.cli', command, argument],
                                cwd=receiver, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    assert (receiver / 'work/repro/sources/rtl/payload').read_text() == 'original'
    assert (unrelated / 'keep').read_text() == 'untouched'


def test_save_dirty_unknown_and_negative_inputs(operator):
    project, caller, definition, data, cli = operator
    cli(project, 'all', definition)
    run, = (project / 'work/smoke/runs').iterdir()
    plan_path = run / 'plan.json'; plan = json.loads(plan_path.read_text())
    plan['definition']['sources'] = [{'name': 'rtl', 'provider': 'git', 'url': '/unavailable'}]
    plan['context']['sources'] = [{'name': 'rtl', 'provider': 'git', 'resolved_revision': 'a'*40}]
    plan_path.write_text(json.dumps(plan))
    record_path = run / 'run.json'; record = json.loads(record_path.read_text())
    record['source_observations'] = {'rtl': {'current_commit': 'b'*40, 'dirty': True}}
    record_path.write_text(json.dumps(record))
    output = caller / 'dirty.yml'
    result = cli(caller, 'save', 'smoke', '--as', 'repro', '--output', output)
    assert 'was dirty' in result.stderr and '# Warning:' in output.read_text()
    assert yaml.safe_load(output.read_text())['sources'][0]['revision'] == 'b'*40
    record.pop('source_observations'); record_path.write_text(json.dumps(record))
    unknown = caller / 'unknown.yml'
    result = cli(caller, 'save', 'smoke', '--as', 'repro', '--output', unknown)
    assert 'HEAD unknown' in result.stderr and 'state unknown' in result.stderr
    assert yaml.safe_load(unknown.read_text())['sources'][0]['revision'] == 'a'*40
    absent = caller / 'absent.yml'
    for options in [('--test', 'missing'), ('--run', 'missing'), ('--run', '../bad')]:
        cli(caller, 'save', 'smoke', '--as', 'repro', '--output', absent, *options, expected=1)
        assert not absent.exists()
    cli(caller, 'save', 'smoke', '--as', 'smoke', '--output', absent, expected=1)
    symlink = caller / 'link.yml'; symlink.symlink_to(absent)
    cli(caller, 'save', 'smoke', '--as', 'repro', '--output', symlink, expected=1)
    assert not absent.exists()
    plan['context']['execution']['adapter'] = 'mock'
    plan_path.write_text(json.dumps(plan))
    cli(caller, 'save', 'smoke', '--as', 'repro', '--output', absent, expected=1)
    assert not absent.exists()


def test_save_failure_never_publishes_partial_file(operator, monkeypatch):
    project, caller, definition, _, cli = operator
    cli(project, 'all', definition)
    output = caller / 'failed.yml'
    def fail(*args):
        raise OSError('injected write failure')
    monkeypatch.setattr('mockingbird.save.os.fsync', fail)
    with pytest.raises(OSError, match='injected'):
        save_plan(plan_target('smoke'), 'repro', output)
    assert not output.exists()
    assert not list(caller.glob('.mb-save-*'))
