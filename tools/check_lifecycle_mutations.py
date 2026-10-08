"""Seed known regressions in temporary copies; require an assertion failure.

Run with the same Python environment as pytest. No mutation tool dependency.
This is a focused sensitivity check, not a general mutation score.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = [
    ('unused directory in prepare', 'context.py',
     'if execution["adapter"] != "command":', 'if True:',
     'test_command_workspace.py::test_command_setup_jobs_and_run_need_no_adapter_workspace'),
    ('unused directory in adapter setup', 'adapters/command.py',
     '"""No adapter-owned preparation; optional YAML setup Jobs run in core."""',
     'Path(context["paths"]["adapter_workdir"]).mkdir(parents=True, exist_ok=True)',
     'test_command_workspace.py::test_command_setup_jobs_and_run_need_no_adapter_workspace'),
    ('plan repeats setup', 'lifecycle.py',
     '    jobs = adapter.plan(context)',
     '    adapter.setup(context)\n    jobs = adapter.plan(context)',
     'test_lifecycle_effects.py::test_replanning_does_not_repeat_setup_or_execute'),
    ('final results collected again', 'lifecycle.py',
     'if entry["state"] == "COMPLETE" or job_id not in by_id:',
     'if job_id not in by_id:',
     'test_lifecycle_effects.py::test_final_collection_does_not_reexecute_or_recollect'),
]


def run_tests(copy, targets):
    report = copy / 'report.xml'
    report.unlink(missing_ok=True)
    env = dict(os.environ, PYTHONPATH=str(copy / 'src'), PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '-q', '-o', 'addopts=',
         '--junitxml=' + str(report), *['tests/' + t for t in targets]],
        cwd=copy, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=120,
    )
    cases = ET.parse(report).getroot().findall('.//testcase') if report.exists() else []
    failures = [c for c in cases if c.find('failure') is not None]
    errors = [c for c in cases if c.find('error') is not None]
    return result, failures, errors


def main():
    with tempfile.TemporaryDirectory(prefix='mb-lifecycle-mutations-') as directory:
        copy = Path(directory)
        for name in ('src', 'tests'):
            shutil.copytree(ROOT / name, copy / name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copy2(ROOT / 'pyproject.toml', copy / 'pyproject.toml')
        targets = ['test_command_workspace.py', 'test_lifecycle_effects.py']
        baseline, _, _ = run_tests(copy, targets)
        if baseline.returncode != 0:
            print('Baseline failed; no mutation result is valid.\n' + baseline.stdout)
            return 1
        for label, relative, old, new, test in MUTATIONS:
            path = copy / 'src' / 'mockingbird' / relative
            original = path.read_text()
            if original.count(old) != 1:
                print('Mutation anchor changed: ' + label)
                return 1
            try:
                path.write_text(original.replace(old, new, 1))
                result, failures, errors = run_tests(copy, [test])
            finally:
                path.write_text(original)
            expected = test.split('::')[1]
            detected = (result.returncode == 1 and not errors and failures
                        and all(c.get('name', '').split('[')[0] == expected for c in failures)
                        and all('AssertionError' in c.find('failure').get('message', '')
                                or 'this phase must not' in c.find('failure').get('message', '')
                                for c in failures))
            if not detected:
                print('NOT DETECTED or invalid failure: ' + label + '\n' + result.stdout)
                return 1
            print('DETECTED: ' + label)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
