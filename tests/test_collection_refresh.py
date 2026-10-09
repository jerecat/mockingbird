import copy
import sys

import pytest
import yaml

from mockingbird import lifecycle, status
from mockingbird.io import read_json
from mockingbird.save import save_plan
from test_review_regressions import definition, ready


def collector(verdict='PASS'):
    return {'command': [sys.executable, '-c',
            f'import json; print(json.dumps({{"status": "{verdict}", "artifacts": ["/tmp/wave.fsdb"]}}))'], 'args': [], 'timeout_s': 2}


def test_refresh_and_save_preserve_execution(tmp_path):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    lifecycle.collect(d, rd)
    evidence = {p: p.read_bytes() for p in [rd / 'run.json', rd / 'plan.json', *rd.glob('jobs/*/execution.json')]}
    d['execution']['collect'] = collector()
    lifecycle.create_plan(d)
    assert lifecycle.collect(d, rd)[0]['jobs']['a']['result']['artifacts'] == []
    result, _ = lifecycle.collect(d, rd, refresh=True)
    assert result['jobs']['a']['result']['artifacts'] == ['/tmp/wave.fsdb']
    assert result['collection_config']['collectors']['a']['command'] == collector()['command']
    assert all(p.read_bytes() == data for p, data in evidence.items())
    save_plan(d, 'exported', tmp_path / 'saved.yml', run_dir=rd)
    exported = yaml.safe_load((tmp_path / 'saved.yml').read_text())
    assert exported['execution']['jobs'][0]['collect']['command'] == collector()['command']
    before = (rd / 'collection.json').read_bytes()
    lifecycle.collect(d, rd)
    assert (rd / 'collection.json').read_bytes() == before


@pytest.mark.parametrize('change', ['args', 'scheduler', 'add', 'remove', 'order', 'metadata'])
def test_refresh_rejection_is_read_only(tmp_path, change):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    lifecycle.collect(d, rd)
    d['execution']['collect'] = collector()
    if change == 'args':
        d['execution']['args'] = ['changed']
    elif change == 'scheduler':
        d['scheduler']['poll_interval_s'] = 1
    elif change == 'add':
        d['execution']['jobs'].append('c')
    elif change == 'remove':
        d['execution']['jobs'].pop()
    elif change == 'order':
        d['execution']['jobs'].reverse()
    else:
        d['execution']['jobs'][0] = {'id': 'a', 'metadata': {'changed': True}}
    lifecycle.create_plan(d)
    before = {p: p.read_bytes() for p in rd.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='non-collector settings changed'):
        lifecycle.collect(d, rd, refresh=True)
    assert all(p.read_bytes() == data for p, data in before.items())


def test_pending_refresh_uses_accepted_settings_after_replan(tmp_path):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    lifecycle.collect(d, rd)
    script = tmp_path / 'collector.py'
    script.write_text('print(\'{"status":"PENDING"}\')')
    d['execution']['collect'] = {'command': [sys.executable, str(script)], 'args': [], 'timeout_s': 2}
    lifecycle.create_plan(d)
    assert lifecycle.collect(d, rd, refresh=True)[0]['summary']['pending'] == 2
    assert status.snapshot(d, rd)['collection_counts']['PENDING'] == 2
    d['execution']['collect'] = collector('FAIL')
    lifecycle.create_plan(d)
    script.write_text('print(\'{"status":"PASS","artifacts":["fixed"]}\')')
    result, _ = lifecycle.collect(d, rd)
    assert result['summary']['pass'] == 2
    assert result['jobs']['a']['result']['artifacts'] == ['fixed']


def test_interrupted_refresh_restarts_with_accepted_contract(tmp_path, monkeypatch):
    from mockingbird.adapters.command import Adapter
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    lifecycle.collect(d, rd)
    d['execution']['collect'] = collector('FAIL')
    lifecycle.create_plan(d)
    original_collect = Adapter.collect
    calls = []
    def interrupt(self, context, executions):
        calls.append(executions[0].job_id)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return original_collect(self, context, executions)
    with monkeypatch.context() as patch:
        patch.setattr(Adapter, 'collect', interrupt)
        with pytest.raises(KeyboardInterrupt):
            lifecycle.collect(d, rd, refresh=True)
    assert status.snapshot(d, rd)['final'] == 1
    assert read_json(rd / 'result.json')['summary']['uncollected'] == 1
    result, _ = lifecycle.collect(d, rd)
    assert result['summary']['fail'] == 2


def test_refresh_acceptance_write_failure_preserves_prior_results(tmp_path, monkeypatch):
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    lifecycle.collect(d, rd)
    d['execution']['collect'] = collector()
    lifecycle.create_plan(d)
    before = {p: p.read_bytes() for p in rd.rglob('*') if p.is_file()}
    real_write = lifecycle.write_json
    def fail(path, data):
        if path == rd / 'collection.json':
            raise OSError('injected publication failure')
        return real_write(path, data)
    monkeypatch.setattr(lifecycle, 'write_json', fail)
    with pytest.raises(OSError, match='publication failure'):
        lifecycle.collect(d, rd, refresh=True)
    assert all(p.read_bytes() == data for p, data in before.items())


def test_refresh_rejects_changed_sources_setup_and_adapter(tmp_path):
    from mockingbird.collection_refresh import refresh_journal
    d = definition(tmp_path)
    ready(d)
    _, rd, _ = lifecycle.run(d)
    original = read_json(rd / 'plan.json')
    run = read_json(rd / 'run.json')
    for field in ('sources', 'setup', 'invocation_dir'):
        changed = copy.deepcopy(original)
        changed['context'][field] = 'changed'
        with pytest.raises(ValueError, match='non-collector settings changed'):
            refresh_journal(original, changed, run, 'now')
    changed = copy.deepcopy(original)
    changed['context']['execution']['adapter'] = 'custom'
    with pytest.raises(ValueError, match='command adapter'):
        refresh_journal(original, changed, run, 'now')


# Run the actual CLI from another directory, including JSON mode and save.
from test_plan_registry import operator


def test_refresh_cli_journey(operator):
    import json
    from pathlib import Path
    project, caller, definition_path, data, cli = operator
    cli(project, 'prepare', definition_path)
    cli(caller, 'plan', 'smoke')
    cli(caller, 'run', 'smoke')
    cli(caller, 'collect', 'smoke')
    state = json.loads(cli(caller, 'status', 'smoke', '--json').stdout)
    run_id = state['run_id']
    rd = Path(state['run_dir'])
    data['execution']['collect'] = collector()
    definition_path.write_text(json.dumps(data))
    cli(caller, 'plan', 'smoke')
    refreshed = json.loads(cli(caller, 'collect', 'smoke', '--run', run_id, '--refresh', '--json').stdout)
    assert refreshed['jobs']['first']['result']['artifacts'] == ['/tmp/wave.fsdb']
    data['execution']['args'] = ['different']
    definition_path.write_text(json.dumps(data))
    cli(caller, 'plan', 'smoke')
    before = (rd / 'result.json').read_bytes()
    rejected = cli(caller, 'collect', 'smoke', '--refresh', expected=1)
    assert '--refresh accepts changes to collect settings only.' in rejected.stderr
    assert 'jobs[first].payload.args' in rejected.stderr
    assert (rd / 'result.json').read_bytes() == before
