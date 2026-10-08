"""CLI rehearsal against a file-backed, project-owned external service."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml


PROJECT = r'''
import json
import os
from pathlib import Path
import sys

root = Path('external')
root.mkdir(exist_ok=True)

def event(value):
    with (root / 'events.jsonl').open('a') as out:
        out.write(json.dumps(value) + '\n')

mode = sys.argv[1]
if mode == 'capacity':
    counter = root / 'capacity-count'
    n = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(n))
    slots = 0 if n <= 2 else 1
    event({'kind': 'capacity', 'slots': slots})
    print(slots)
    sys.exit(0)

job = os.environ['MB_JOB_ID']
run = os.environ['MB_RUN_ID']
assert sys.argv[2] == job
folder = root / run
folder.mkdir(exist_ok=True)
result = folder / (job + '.json')
event({'kind': mode, 'run': run, 'job': job})
if mode == 'submit':
    if job == 'cleanup':
        sys.exit(9)  # Deliberate execution failure; no-check must not infer FAIL.
    if job.startswith('sim_') and job != 'sim_late':
        status = 'FAIL' if job == 'sim_fail' and not (root / 'repaired').exists() else 'PASS'
        result.write_text(json.dumps({'status': status, 'artifacts': ['external://' + run + '/' + job]}))
    sys.exit(0)  # Submission has returned, regardless of the eventual test result.

counter = folder / (job + '.attempts')
n = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(n))
if job == 'sim_retry' and n == 1:
    print('temporary result service failure', file=sys.stderr)
    sys.exit(7)
print(result.read_text() if result.exists() else json.dumps({'status': 'PENDING'}))
'''


def test_virtual_operator_lifecycle(tmp_path):
    project = tmp_path / 'project.py'
    project.write_text(PROJECT)
    ids = ['compile', 'pause', 'sim_pass', 'sim_late', 'sim_fail', 'sim_retry', 'cleanup']
    definition = {
        'plan': 'virtual-nightly',
        'sources': [],
        'execution': {
            'defaults': {
                'command': [sys.executable, str(project), 'submit'],
                'timeout_s': 5,
                'collect': {'command': [sys.executable, str(project), 'collect'], 'timeout_s': 5},
            },
            'jobs': [
                {'id': 'compile', 'collect': {'mode': 'no-check'}},
                {
                    'id': 'pause',
                    'command': [sys.executable, '-c', 'import time;time.sleep(0.01)'],
                    'args': [],
                    'collect': {'mode': 'no-check'},
                },
                'sim_pass',
                'sim_late',
                'sim_fail',
                'sim_retry',
                {'id': 'cleanup', 'collect': {'mode': 'no-check'}},
            ],
        },
        'scheduler': {
            'capacity_provider': 'command',
            'max_parallel': 1,
            'poll_interval_s': 0.001,
            'config': {'command': [sys.executable, str(project), 'capacity'], 'timeout_s': 5},
        },
    }
    path = tmp_path / 'regression.yaml'
    path.write_text(yaml.safe_dump(definition, sort_keys=False))
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    transcript = []

    def cli(command, *args, expected=0, config=path):
        result = subprocess.run([sys.executable, '-m', 'mockingbird.cli', command, (str(config) if command in {'prepare', 'doctor', 'all'} else yaml.safe_load(config.read_text())['plan']), *map(str, args)],
                                cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
        transcript.append({'command': command, 'args': list(map(str, args)), 'exit': result.returncode,
                           'stdout': result.stdout, 'stderr': result.stderr})
        assert result.returncode == expected, transcript[-1]
        return result

    def read(path):
        return json.loads(path.read_text())

    def events():
        return [json.loads(line) for line in (tmp_path / 'external/events.jsonl').read_text().splitlines()]

    def current_run():
        return Path(read(tmp_path / 'work/virtual-nightly/.reg/last_run.json')['run_dir'])

    cli('doctor')
    # Reset the fake capacity source after its doctor probe for deterministic steps.
    (tmp_path / 'external/capacity-count').unlink()
    (tmp_path / 'external/events.jsonl').write_text('')
    cli('prepare')
    cli('setup')
    cli('plan')
    plan = read(tmp_path / 'work/virtual-nightly/.reg/plan.json')
    assert [job['id'] for job in plan['jobs']] == ids
    assert all(set(job['payload']) == {'command', 'args', 'args_suffix', 'timeout_s', 'collect'} for job in plan['jobs'])
    cli('dry-run')
    assert not any(e['kind'] == 'submit' for e in events())

    cli('run')
    first_run = current_run()
    original_executions = (first_run / 'executions.json').read_bytes()
    executed = json.loads(original_executions)
    assert [e['job_id'] for e in executed] == ids
    assert executed[-1]['observation']['returncode'] == 9
    timeline = events()
    assert timeline[:2] == [{'kind': 'capacity', 'slots': 0}] * 2
    assert [e['job'] for e in timeline if e['kind'] == 'submit'] == [j for j in ids if j != 'pause']
    submission_count = sum(e['kind'] == 'submit' for e in timeline)

    snapshots = []
    def collect(label, expected):
        cli('collect', '--run-dir', first_run, expected=expected)
        result = read(first_run / 'result.json')
        snapshots.append({'cycle': label, 'status': result['status'], **result['summary']})
        assert (first_run / 'executions.json').read_bytes() == original_executions
        assert sum(e['kind'] == 'submit' for e in events()) == submission_count
        return result

    first = collect('first', 2)
    assert first['summary'] == {'total': 7, 'pass': 4, 'fail': 1, 'error': 0, 'skip': 0,
                                'pending': 1, 'uncollected': 0, 'collection_error': 1}
    final_ids = {test['id'] for test in first['tests']}
    assert {'compile', 'pause', 'cleanup'}.issubset(final_ids)
    assert not {'sim_late', 'sim_retry'} & final_ids
    boundary = len(events())
    second = collect('retry service', 2)
    assert [e['job'] for e in events()[boundary:] if e['kind'] == 'collect'] == ['sim_late', 'sim_retry']
    assert second['summary']['pass'] == 5 and second['summary']['pending'] == 1
    assert second['summary']['collection_error'] == 0

    # Operator publishes the delayed external result; no MB execution occurs.
    (tmp_path / 'external' / first_run.name / 'sim_late.json').write_text(json.dumps({'status': 'PASS'}))
    boundary = len(events())
    third = collect('late result arrives', 1)
    assert [e['job'] for e in events()[boundary:] if e['kind'] == 'collect'] == ['sim_late']
    assert third['collection_complete'] and third['summary']['pass'] == 6 and third['summary']['fail'] == 1
    boundary = len(events())
    journal = (first_run / 'collection.json').read_bytes()
    fourth = collect('already complete', 1)
    assert len(events()) == boundary
    assert (first_run / 'collection.json').read_bytes() == journal
    assert third['tests'] == fourth['tests']
    cli('status', '--run-dir', first_run)

    # Repair outside MB, then rerun only the final FAIL as a new run.
    prior_result = (first_run / 'result.json').read_bytes()
    (tmp_path / 'external/repaired').touch()
    cli('run', '--failed-from', first_run)
    retry_run = current_run()
    assert retry_run != first_run
    retry_record = read(retry_run / 'run.json')
    assert retry_record['selection']['selected_ids'] == ['sim_fail']
    assert retry_record['selection']['failed_from_run_id'] == first_run.name
    assert retry_record['selection']['failed_from_sha256'] == hashlib.sha256(prior_result).hexdigest()
    cli('collect', '--run-dir', retry_run)
    retry_result = read(retry_run / 'result.json')
    assert retry_result['status'] == 'PASS' and retry_result['summary']['total'] == 1
    assert (first_run / 'result.json').read_bytes() == prior_result
    assert retry_result['tests'][0]['artifacts'] == ['external://' + retry_run.name + '/sim_fail']

    # A malformed contract is rejected in plan, with no accidental submissions.
    definition['plan'] = 'bad'
    definition['execution']['jobs'][0]['timeuot_s'] = 5
    bad = tmp_path / 'bad.yaml'
    bad.write_text(yaml.safe_dump(definition))
    cli('prepare', config=bad)
    cli('setup', config=bad)
    boundary = len(events())
    cli('plan', config=bad, expected=1)
    cli('run', config=bad, expected=1)
    assert len(events()) == boundary

    report = {'scenario': 'virtual-nightly', 'cycles': snapshots, 'rerun': retry_result['summary'],
              'checks': ['list order', 'capacity zero gate', 'frozen contracts', 'execution/result separation',
                         'pending retry', 'collector error retry', 'immutable final results',
                         'no executor rerun during collect', 'failed-only rerun provenance', 'plan validation']}
    (tmp_path / 'operations-report.json').write_text(json.dumps(report, indent=2))
    (tmp_path / 'cli-transcript.json').write_text(json.dumps(transcript, indent=2))
    print(json.dumps(report, indent=2))
