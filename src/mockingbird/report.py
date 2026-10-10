"""Read-only report projection. Never invokes execution or collection."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from .context import run_root_path
from .io import read_json


def load_report(defn, *, runs=(), exclude=(), last=None, since=None, until=None):
    if last is not None and last < 1:
        raise ValueError('--last must be positive')
    start = date.fromisoformat(since) if since else None
    end = date.fromisoformat(until) if until else None
    if start and end and start > end:
        raise ValueError('--since must not be after --until')
    root = run_root_path(defn)
    available = {p.name: p for p in root.iterdir() if p.is_dir() and (p / 'run.json').is_file()} if root.exists() else {}
    unknown = (set(runs) | set(exclude)) - available.keys()
    if unknown:
        raise ValueError('Unknown run ID(s): ' + ', '.join(sorted(unknown)))
    candidates = []
    for name, path in available.items():
        if name in exclude or (runs and name not in runs):
            continue
        record = read_json(path / 'run.json')
        stamp = datetime.fromisoformat(record['started_at'])
        if stamp.tzinfo is None:
            raise ValueError(f'{name}: started_at must include timezone')
        day = stamp.astimezone().date()
        if (start and day < start) or (end and day > end):
            continue
        candidates.append((stamp, name, path, record))
    candidates.sort(key=lambda item: (item[0], item[1]))
    if last:
        candidates = candidates[-last:]
    if not candidates:
        raise ValueError('No runs match the report selection')
    output = []
    for _, name, path, record in candidates:
        if record['run_id'] != name or record['plan'] != defn['plan']:
            raise ValueError(f'{name}: run identity mismatch')
        ids = record['selection']['selected_ids']
        if len(ids) != len(set(ids)) or set(ids) != set(record['jobs']):
            raise ValueError(f'{name}: run selection mismatch')
        result = read_json(path / 'result.json') if (path / 'result.json').exists() else None
        if result is not None and (result['run_id'] != name or result['plan'] != record['plan'] or set(result['jobs']) != set(ids)):
            raise ValueError(f'{name}: run/result identity or selected IDs mismatch')
        plan = read_json(path / 'plan.json')
        if plan['plan'] != record['plan']:
            raise ValueError(f'{name}: plan identity mismatch')
        definitions = {j['id']: j['payload'] for j in plan['jobs']}
        if not set(ids).issubset(definitions):
            raise ValueError(f'{name}: selected IDs missing from saved plan')
        tests = {}
        for job in ids:
            entry = result['jobs'][job] if result else {'state': 'UNCOLLECTED'}
            state = entry['state']
            value = entry.get('result', {}) if state == 'COMPLETE' else entry
            if state == 'COMPLETE':
                if value.get('id') != job or value.get('status') not in {'PASS', 'FAIL', 'ERROR', 'SKIP'}:
                    raise ValueError(f'{name}: invalid result for {job}')
                status = value['status']
            else:
                if state not in {'PENDING', 'ERROR', 'UNCOLLECTED'}:
                    raise ValueError(f'{name}: invalid collection state for {job}')
                status = 'COLLECTION_ERROR' if state == 'ERROR' else state
            tests[job] = dict(status=status, reason=value.get('reason') or '', artifacts=value.get('artifacts', []), duration=value.get('duration_s'), definition=definitions[job])
        output.append(dict(id=name, started=record['started_at'], execution=record['status'], collected=result.get('generated_at') if result else None, tests=tests))
    return dict(plan=defn['plan'], generated=datetime.now().astimezone().isoformat(), runs=output, ids=sorted({j for r in output for j in r['tests']}))


def generate_report(defn, output=None, **selection):
    data = load_report(defn, **selection)
    destination = Path(output) if output else run_root_path(defn).parent / 'report.html'
    # Never allow a report to overwrite saved evidence, even through a symlink.
    target = destination.resolve()
    root = run_root_path(defn).resolve()
    if target == root or root in target.parents or destination.suffix.lower() != '.html':
        raise ValueError('Report output must be an .html file outside the runs directory')
    template = Path(__file__).with_name('report.html').read_text(encoding='utf-8')
    payload = json.dumps(data, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html = template.replace('__REPORT_DATA__', payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding='utf-8')
    return destination.resolve(), len(data['runs']), len(data['ids'])
