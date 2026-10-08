"""Capacity commands use the same saved invocation directory as execution."""
import json
from pathlib import Path
import sys

from mockingbird import lifecycle
from mockingbird.context import load_definition, prepare
from mockingbird.doctor import doctor_failed, run_doctor


def test_capacity_and_execution_use_prepared_cwd_from_another_directory(tmp_path, monkeypatch):
    prepared = tmp_path / 'prepared'; prepared.mkdir()
    caller = tmp_path / 'caller'; caller.mkdir()
    (prepared / 'slots.py').write_text("from pathlib import Path; Path('capacity-used').touch(); print(1)")
    # If capacity accidentally uses the caller's script, fail immediately rather than wait.
    (caller / 'slots.py').write_text("raise SystemExit(7)")
    path = prepared / 'jobs.yaml'
    path.write_text(json.dumps({
        'plan': 'test',
        'execution': {
            'command': [sys.executable, '-c', "from pathlib import Path; Path('run-used').touch()"],
            'args': [],
            'timeout_s': 2,
            'jobs': ['job'],
        },
        'scheduler': {'capacity_provider': 'command', 'config': {'command': [sys.executable, 'slots.py']}},
    }))
    monkeypatch.chdir(prepared)
    definition = load_definition(path)
    prepare(definition); lifecycle.create_plan(definition)
    monkeypatch.chdir(caller)
    assert not doctor_failed(run_doctor(definition))  # provisional context binds supplied invocation
    assert (prepared/'capacity-used').exists()
    (prepared/'capacity-used').unlink()
    executions, _, _ = lifecycle.run(definition)
    assert executions[0].observation['returncode'] == 0
    assert (prepared/'capacity-used').exists() and (prepared/'run-used').exists()
    assert not (caller/'capacity-used').exists() and not (caller/'run-used').exists()
