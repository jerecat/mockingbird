from pathlib import Path
import sys

from mockingbird import lifecycle
from mockingbird.context import prepare
from test_review_regressions import definition


def test_command_setup_jobs_and_run_need_no_adapter_workspace(tmp_path):
    d = definition(tmp_path)
    d['setup'] = {'jobs': [{'id': 'setup', 'command': [sys.executable, '-c', 'pass'],
                           'args': [], 'timeout_s': 2}]}
    context = prepare(d)
    unused = Path(context['paths']['adapter_workdir'])
    assert not unused.exists()
    lifecycle.setup(d)
    lifecycle.create_plan(d)
    executions, _, _ = lifecycle.run(d)
    assert all(e.observation['returncode'] == 0 for e in executions)
    assert not unused.exists()


def test_prepare_preserves_existing_user_files_in_exec(tmp_path):
    d = definition(tmp_path)
    old = tmp_path / 'work/A/exec'
    old.mkdir(parents=True)
    (old / 'user.txt').write_text('keep')
    prepare(d)
    lifecycle.setup(d)
    assert (old / 'user.txt').read_text() == 'keep'


def test_custom_adapter_keeps_prepared_workspace(tmp_path):
    d = definition(tmp_path)
    d['execution'] = {'adapter': 'demo_linux', 'config': {'tests': []}}
    context = prepare(d)
    assert Path(context['paths']['adapter_workdir']).is_dir()
    lifecycle.setup(d)
    lifecycle.create_plan(d)
