"""Export saved execution contracts, without preparing or running anything."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile

import yaml

from . import registry
from .context import validate_definition_identity
from .io import read_json
from .lifecycle import _resolve_run_dir
from .plugins import load_adapter, load_source_provider


def save_plan(defn, new_name, output, *, run_dir=None, test_ids=None):
    registry.plan_name(new_name)
    if new_name == defn['plan']:
        raise ValueError('--as must name a different plan')
    if registry.lookup(new_name) is not None:
        raise ValueError(f'plan {new_name!r} is already registered; choose an unused --as name')
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'output already exists: {output}')
    run_path = _resolve_run_dir(defn, run_dir)
    record = read_json(run_path / 'run.json')
    plan = read_json(run_path / 'plan.json')
    if record.get('schema_version') != 3 or plan.get('schema_version') != 3:
        raise ValueError('save requires schema-3 run and plan records')
    validate_definition_identity(defn, record)
    validate_definition_identity(defn, plan)
    context = plan['context']
    selected = record['selection']['selected_ids']
    requested = set(test_ids) if test_ids else set(selected)
    unknown = requested - set(selected)
    if unknown:
        raise ValueError(f'Jobs were not selected in this run: {sorted(unknown)}')
    jobs = [job for job in plan['jobs'] if job['id'] in requested]
    if not jobs or {job['id'] for job in jobs} != requested:
        raise ValueError('saved run has no exportable Jobs or inconsistent Job records')
    adapter = load_adapter(context['execution']['adapter'])
    export = getattr(adapter, 'export_jobs', None)
    if export is None:
        raise ValueError('execution adapter does not support saving resolved Jobs')
    jobs = copy.deepcopy(jobs)
    journal_path = run_path / 'collection.json'
    journal = read_json(journal_path) if journal_path.exists() else {}
    if 'collectors' in journal:
        for job in jobs:
            job['payload']['collect'] = copy.deepcopy(journal['collectors'][job['id']])
    execution = export(jobs)
    definition = copy.deepcopy(plan['definition'])
    definition.update(plan=new_name, execution=execution)
    warnings = []
    prepared = {source['name']: source for source in context.get('sources', [])}
    observations = record.get('source_observations', {})
    for source in definition.get('sources', []):
        provider = load_source_provider(source['provider'])
        pin = getattr(provider, 'export_source', None)
        if pin is None:
            warnings.append(f"source {source['name']!r}: provider cannot pin run-time state; original settings retained")
        else:
            warnings.extend(pin(source, prepared.get(source['name'], {}), observations.get(source['name'], {})))
    comments = [f'Saved from plan {defn["plan"]}, run {record["run_id"]}.',
                'Review paths, tools, build inputs and seeds for the receiving environment.',
                'Use a fresh plan workspace; prepare never resets existing sources.',
                'Selected Jobs may depend on other Jobs; dependencies are not inferred.']
    comments.extend('Warning: ' + warning for warning in warnings)
    header = ''.join('# ' + line + '\n' for comment in comments for line in comment.splitlines())
    text = header + yaml.safe_dump(definition, sort_keys=False, allow_unicode=True)
    # Publish complete content without ever replacing an existing file/symlink.
    fd, temporary = tempfile.mkstemp(prefix='.mb-save-', dir=output.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        os.unlink(temporary)
    return {'run_id': record['run_id'], 'jobs': len(jobs), 'warnings': warnings}
