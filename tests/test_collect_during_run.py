"""The ordinary collect command consumes saved executions while run progresses."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
import yaml

from mockingbird import lifecycle
from mockingbird.io import read_json, write_json
from test_collection_cycles import make_run


def wait_for(path, process):
    deadline = time.monotonic() + 15
    while not path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists(), f"did not reach {path.name}; process status={process.poll()}"


@pytest.mark.parametrize('refresh', [False, True])
def test_cli_collect_overlaps_run_and_retries_only_unresolved(tmp_path, refresh):
    # Real independent CLI processes; explicit gates, not guessed sleep durations.
    (tmp_path / 'execute.py').write_text('''import pathlib, sys, time
job = sys.argv[1]
with open('executed.txt', 'a') as f: f.write(job + '\\n')
if job in ('a', 'd'):
    pathlib.Path(job + '.started').touch()
    deadline = time.monotonic() + 30
    while not pathlib.Path(job + '.release').exists():
        if time.monotonic() > deadline: raise RuntimeError('test gate timed out')
        time.sleep(0.01)
''')
    (tmp_path / 'collector.py').write_text('''import json, os, pathlib, sys, time
job = os.environ['MB_JOB_ID']
evidence = json.loads(pathlib.Path(os.environ['MB_EXECUTION_JSON']).read_text())
assert evidence['job_id'] == job
p = pathlib.Path(job + '.calls')
n = int(p.read_text()) + 1 if p.exists() else 1
p.write_text(str(n))
if job == 'b' and pathlib.Path('block-collector').exists():
    pathlib.Path('collector.started').touch()
    deadline = time.monotonic() + 30
    while not pathlib.Path('collector.release').exists():
        if time.monotonic() > deadline: raise RuntimeError('collector gate timed out')
        time.sleep(0.01)
if job == 'c' and n == 1: sys.exit(7)
status = 'PENDING' if job == 'b' and not pathlib.Path('b.done').exists() else 'PASS'
print(json.dumps({'status': status}))
''')
    definition = tmp_path / 'regression.yaml'
    definition.write_text(yaml.safe_dump({
        'plan': 'live',
        'execution': {
            'defaults': {'command': [sys.executable, str(tmp_path / 'execute.py')],
                         'timeout_s': 40,
                         'collect': {'command': [sys.executable, str(tmp_path / 'collector.py')],
                                     'timeout_s': 40}},
            'jobs': ['a', 'b', 'c', 'd'],
        },
        'scheduler': {'capacity_provider': 'fixed', 'config': {'slots': 1}},
    }))
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    caller = tmp_path / 'another-terminal'
    caller.mkdir()
    command = [sys.executable, '-m', 'mockingbird.cli']

    def cli(*args, expected=0, cwd=caller):
        p = subprocess.run(command + list(args), cwd=cwd, env=env,
                           capture_output=True, text=True, timeout=15)
        assert p.returncode == expected, p.stdout + p.stderr
        return p

    cli('prepare', str(definition), cwd=tmp_path)
    cli('plan', 'live')
    processes = []
    try:
        runner = subprocess.Popen(command + ['run', 'live'], cwd=caller, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        processes.append(runner)
        wait_for(tmp_path / 'a.started', runner)
        rd = Path(read_json(tmp_path / 'work/live/.reg/last_run.json')['run_dir'])
        run_before = (rd / 'run.json').read_bytes()
        assert read_json(rd / 'run.json')['status'] == 'RUNNING'
        assert not (rd / 'executions.json').exists()
        # No saved executions yet: normal incomplete collection, not an error.
        options = ['--refresh'] if refresh else []
        first = json.loads(cli('collect', 'live', *options, '--json', expected=2).stdout)
        assert first['summary']['uncollected'] == 4
        assert all(j['attempts'] == 0 for j in first['jobs'].values())
        assert not list(tmp_path.glob('*.calls'))
        (tmp_path / 'a.release').touch()
        wait_for(tmp_path / 'd.started', runner)
        evidence = {p: p.read_bytes() for p in rd.glob('jobs/*/execution.json')}
        assert len(evidence) == 3
        partial_output = cli('collect', 'live', '--run', rd.name, expected=2).stdout
        assert 'Collection: 1/4 complete' in partial_output
        assert 'Result:' not in partial_output
        assert 'collect again as records arrive' in partial_output
        assert partial_output.count('Next: mb collect') == 1
        partial = read_json(rd / 'result.json')
        assert partial['summary'] == dict(total=4, **{'pass': 1}, fail=0, error=0,
                                          skip=0, pending=1, collection_error=1, uncollected=1)
        assert partial['jobs']['d']['attempts'] == 0
        assert (rd / 'run.json').read_bytes() == run_before
        observed = json.loads(cli('status', 'live', '--json').stdout)
        assert observed['execution_status'] == 'RUNNING'
        assert observed['recorded'] == 3 and observed['final'] == 1
        assert 'Next: mb collect' in cli('status', 'live').stdout

        # Hold a collector after its execution snapshot. Run may finish meanwhile.
        (tmp_path / 'block-collector').touch()
        (tmp_path / 'b.done').touch()
        collector = subprocess.Popen(command + ['collect', 'live', '--json'], cwd=caller,
                                     env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True)
        processes.append(collector)
        wait_for(tmp_path / 'collector.started', collector)
        duplicate = cli('collect', 'live', expected=1)
        assert 'collection is already running' in duplicate.stderr
        (tmp_path / 'd.release').touch()
        stdout, stderr = runner.communicate(timeout=15)
        assert runner.returncode == 0, stdout + stderr
        assert 'Collection: not started' not in stdout
        assert read_json(rd / 'run.json')['status'] == 'EXECUTED'
        terminal_record = (rd / 'run.json').read_bytes()
        assert all(p.read_bytes() == data for p, data in evidence.items())
        (tmp_path / 'collector.release').touch()
        stdout, stderr = collector.communicate(timeout=15)
        assert collector.returncode == 2, stdout + stderr
        overlapping = json.loads(stdout)
        assert overlapping['summary']['pass'] == 3
        assert overlapping['summary']['uncollected'] == 1
        assert (rd / 'run.json').read_bytes() == terminal_record
        # The new checkpoint missed by this sweep is picked up next time.
        final = json.loads(cli('collect', 'live', '--json').stdout)
        assert final['status'] == 'PASS' and final['collection_complete']
        assert [final['jobs'][j]['attempts'] for j in 'abcd'] == [1, 2, 2, 1]
        again = json.loads(cli('collect', 'live', '--json').stdout)
        assert again['jobs'] == final['jobs']
        assert [int((tmp_path / (j + '.calls')).read_text()) for j in 'abcd'] == [1, 2, 2, 1]
        assert (tmp_path / 'executed.txt').read_text().splitlines() == list('abcd')
        assert (rd / 'run.json').read_bytes() == terminal_record
        assert all(p.read_bytes() == data for p, data in evidence.items())
    finally:
        for name in ('a.release', 'd.release', 'collector.release'):
            (tmp_path / name).touch()
        for process in processes:
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)


@pytest.mark.parametrize('state,legacy', [('RUNNING', True), ('UNKNOWN', False)])
def test_invalid_or_legacy_active_run_still_rejected(tmp_path, monkeypatch, state, legacy):
    d = make_run(tmp_path, monkeypatch)
    _, rd, _ = lifecycle.run(d)
    record = read_json(rd / 'run.json')
    record['status'] = state
    if legacy:
        record.pop('checkpoint_storage')
    write_json(rd / 'run.json', record)
    with pytest.raises(RuntimeError, match='not collectable'):
        lifecycle.collect(d, rd)
    assert not (rd / 'result.json').exists()


def test_collect_at_atomic_execution_publication_boundary(tmp_path, monkeypatch):
    from mockingbird import io
    d = make_run(tmp_path, monkeypatch, ['a'])
    replace = io.os.replace
    observations = []

    def observe_before_publish(src, dst):
        if Path(dst).name == 'execution.json':
            # A complete temporary file is still not published execution evidence.
            observations.append(lifecycle.collect(d)[0])
        replace(src, dst)

    monkeypatch.setattr(io.os, 'replace', observe_before_publish)
    _, rd, _ = lifecycle.run(d)
    assert len(observations) == 1
    assert observations[0]['summary']['uncollected'] == 1
    assert observations[0]['jobs']['a']['attempts'] == 0
    final, _ = lifecycle.collect(d, rd)
    assert final['status'] == 'PASS' and final['jobs']['a']['attempts'] == 1
