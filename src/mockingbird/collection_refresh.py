"""Explicit collector repair without changing execution evidence."""
from __future__ import annotations

import copy
import json
import shlex


def comparable(plan):
    context = copy.deepcopy(plan['context'])
    for key in ('prepared_at', 'definition_path', 'orchestrator'):
        context.pop(key, None)
    # Compare resolved Jobs instead of shorthand/default spellings.
    context['execution'].pop('config', None)
    jobs = copy.deepcopy(plan['jobs'])
    for job in jobs:
        job['payload'].pop('collect', None)
    return {'context': context, 'jobs': jobs, 'meta': plan.get('meta', {})}


def differences(old, new, path=''):
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(old.keys() | new.keys()):
            child = f'{path}.{key}' if path else key
            if key not in old or key not in new:
                yield child, old.get(key), new.get(key)
            else:
                yield from differences(old[key], new[key], child)
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for index, (left, right) in enumerate(zip(old, new)):
            label = left.get('id', index) if isinstance(left, dict) else index
            yield from differences(left, right, f'{path}[{label}]')
    elif old != new:
        yield path, old, new


def refresh_journal(original, latest, run, now):
    if (original.get('schema_version') != 3 or run.get('checkpoint_storage') != 'per-job'
            or original['context']['execution']['adapter'] != 'command'
            or latest['context']['execution']['adapter'] != 'command'):
        raise ValueError('--refresh requires a schema-3 run using the command adapter')
    changes = list(differences(comparable(original), comparable(latest)))
    if changes:
        lines = ['Cannot refresh collectors: non-collector settings changed.', '']
        for path, old, new in changes:
            lines.extend([f'  {path}', f'    Run:  {json.dumps(old)}', f'    Plan: {json.dumps(new)}'])
        target = shlex.quote(run['plan'])
        lines.extend(['', '--refresh accepts changes to collect settings only.',
                      'Non-collector settings also changed, so collection was not started.',
                      f'Restore the other settings and run: mb plan {target}',
                      f'Then retry: mb collect {target} --run {shlex.quote(run["run_id"])} --refresh',
                      'Existing collection records and results were not changed.'])
        raise ValueError('\n'.join(lines))
    jobs = {job['id']: job for job in latest['jobs']}
    selected = run['selection']['selected_ids']
    return {'schema_version': 2, 'run_id': run['run_id'], 'refreshed_at': now,
            'collectors': {key: copy.deepcopy(jobs[key]['payload']['collect']) for key in selected},
            'jobs': {key: {'state': 'UNCOLLECTED', 'attempts': 0} for key in selected}}
