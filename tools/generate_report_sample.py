"""Generate the checked-in synthetic HTML through the production report renderer.

Run from the repository root: PYTHONPATH=src python tools/generate_report_sample.py
No simulations or collectors are executed; temporary JSON fixtures are discarded.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from mockingbird.context import run_root_path
from mockingbird.report import generate_report


def main():
    destination = Path(__file__).resolve().parents[1] / 'Documentation/examples/report-sample.html'
    with TemporaryDirectory(prefix='mb-report-sample-') as directory:
        definition = {'plan': 'soc-nightly-synthetic', '_invocation_dir': directory}
        root = run_root_path(definition)
        ids = [f'{block}.{case}' for block in ('cpu', 'smmu', 'pcie', 'ddr', 'gic', 'reset')
               for case in ('basic', 'boundary', 'stress', 'recovery')]
        for number in range(1, 7):
            run_id = f'2026100{number}_060000_synthetic'
            path = root / run_id
            path.mkdir(parents=True)
            selected = ids[:-2] if number < 3 else [i for i in ids if number != 5 or i != 'cpu.stress']
            jobs = {}
            for index, job in enumerate(selected):
                verdict = 'PASS'
                if job == 'smmu.boundary' and number < 4:
                    verdict = 'FAIL'
                if job == 'pcie.stress' and number >= 5:
                    verdict = 'FAIL'
                if job == 'ddr.recovery' and number == 6:
                    verdict = 'ERROR'
                if job == 'reset.recovery':
                    verdict = 'SKIP'
                entry = {'state': 'COMPLETE', 'result': {
                    'id': job, 'status': verdict, 'duration_s': 30 + index * 7,
                    'reason': {'PASS': 'All checks passed (synthetic)', 'FAIL': 'Data mismatch (synthetic)',
                               'ERROR': 'Test reported an internal error (synthetic)', 'SKIP': 'Disabled in this configuration (synthetic)'}[verdict],
                    'artifacts': [f'/synthetic/soc/{run_id}/{job}/sim.log', f'/synthetic/soc/{run_id}/{job}/wave.fsdb']}}
                if number == 6 and job in {'gic.stress', 'reset.basic', 'cpu.recovery'}:
                    entry = {'state': {'gic.stress': 'PENDING', 'reset.basic': 'UNCOLLECTED', 'cpu.recovery': 'ERROR'}[job],
                             'reason': 'Synthetic incomplete collection example', 'artifacts': []}
                jobs[job] = entry
            records = {
                'run.json': {'run_id': run_id, 'plan': definition['plan'], 'started_at': f'2026-10-0{number}T06:00:00+09:00',
                             'status': 'EXECUTED', 'selection': {'selected_ids': selected}, 'jobs': {j: {} for j in selected}},
                'plan.json': {'plan': definition['plan'], 'jobs': [{'id': j, 'payload': {'command': ['synthetic-simulator'],
                              'args': [j], 'timeout_s': 600 if number < 4 else 600 if j != 'ddr.basic' else 900}} for j in selected]},
                'result.json': {'run_id': run_id, 'plan': definition['plan'], 'generated_at': f'2026-10-0{number}T07:00:00+09:00', 'jobs': jobs}}
            for name, data in records.items():
                (path / name).write_text(json.dumps(data), encoding='utf-8')
        output, _, _ = generate_report(definition, destination)
        # Stabilize only the export timestamp so regeneration produces a reviewable diff.
        html = output.read_text(encoding='utf-8')
        import re
        html = re.sub(r'"generated": "[^"]+"', '"generated": "2026-10-06T08:00:00+09:00 (synthetic sample)"', html, count=1)
        output.write_text(html, encoding='utf-8')
        print(output)


if __name__ == '__main__':
    main()
