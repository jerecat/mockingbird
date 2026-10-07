"""User-facing lifecycle invariants, including forbidden side effects."""
import subprocess

import pytest

from mockingbird import lifecycle, status
from mockingbird.adapters.command import Adapter
from mockingbird.context import prepare
from mockingbird.errors import PlanChangedError
from test_review_regressions import definition


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() if p.is_file() else None
            for p in root.rglob('*')}


def forbidden(*args, **kwargs):
    pytest.fail('this phase must not launch a process or invoke setup')


@pytest.mark.parametrize('empty_setup', [False, True])
def test_replanning_does_not_repeat_setup_or_execute(tmp_path, monkeypatch, empty_setup):
    d = definition(tmp_path)
    if empty_setup:
        d['setup'] = {'jobs': []}
    prepare(d)
    user_file = tmp_path / 'work' / 'user.txt'
    user_file.write_text('local edits')
    with monkeypatch.context() as patch:
        patch.setattr(subprocess, 'Popen', forbidden)
        patch.setattr(Adapter, 'setup', forbidden)
        assert lifecycle.setup(d) is None
        first = lifecycle.create_plan(d)
        second = lifecycle.create_plan(d)
    assert first['jobs'] == second['jobs']
    assert user_file.read_text() == 'local edits'
    assert not (tmp_path / 'work' / 'exec').exists()
    assert not list((tmp_path / 'runs').rglob('execution.json'))


def test_stale_plan_rejected_before_any_run_side_effect(tmp_path, monkeypatch):
    d = definition(tmp_path)
    prepare(d)
    lifecycle.create_plan(d)
    before = tree(tmp_path)
    d['execution']['args'] = ['changed']
    with monkeypatch.context() as patch:
        patch.setattr(subprocess, 'Popen', forbidden)
        with pytest.raises(PlanChangedError):
            lifecycle.run(d)
    assert tree(tmp_path) == before


@pytest.mark.parametrize('collected', [False, True])
def test_status_is_read_only(tmp_path, monkeypatch, collected):
    d = definition(tmp_path)
    prepare(d)
    lifecycle.create_plan(d)
    _, run_dir, _ = lifecycle.run(d)
    if collected:
        lifecycle.collect(d, run_dir)
    before = tree(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(subprocess, 'Popen', forbidden)
        patch.setattr(Adapter, 'collect', forbidden)
        observation = status.snapshot(d, run_dir)
    assert observation['recorded'] == 2
    assert observation['final'] == (2 if collected else 0)
    assert tree(tmp_path) == before


def test_final_collection_does_not_reexecute_or_recollect(tmp_path, monkeypatch):
    d = definition(tmp_path)
    prepare(d)
    lifecycle.create_plan(d)
    _, run_dir, _ = lifecycle.run(d)
    first, _ = lifecycle.collect(d, run_dir)
    evidence = {p: p.read_bytes() for p in run_dir.rglob('execution.json')}
    with monkeypatch.context() as patch:
        patch.setattr(subprocess, 'Popen', forbidden)
        patch.setattr(Adapter, 'execute', forbidden)
        patch.setattr(Adapter, 'collect', forbidden)
        second, _ = lifecycle.collect(d, run_dir)
    assert second['summary'] == first['summary']
    assert second['collection'] == first['collection']
    assert all(p.read_bytes() == contents for p, contents in evidence.items())
