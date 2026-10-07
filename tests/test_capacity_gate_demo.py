"""Observe serial submission pause at two external Jobs, then resume."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


REPO = Path(__file__).resolve().parents[1]


def environment(tmp_path):
    (tmp_path / "examples").mkdir()
    for name in ("capacity-gate.yaml", "sample_queue.py"):
        shutil.copyfile(REPO / "examples" / name, tmp_path / "examples" / name)
    return dict(os.environ, PYTHONPATH=str(REPO / "src"))


def test_capacity_pause_finish_resume_and_collect(tmp_path):
    env = environment(tmp_path)
    def mb(command, *args, expected=0):
        result = subprocess.run([sys.executable, "-m", "mockingbird.cli", command,
                                 "examples/capacity-gate.yaml", *args], cwd=tmp_path, env=env,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == expected, result.stdout + result.stderr
        return result
    def queue(*args, expected=0, **identity):
        result = subprocess.run([sys.executable, "examples/sample_queue.py", *args],
                                cwd=tmp_path, env=dict(env, **identity), capture_output=True,
                                text=True, timeout=5)
        assert result.returncode == expected, result.stdout + result.stderr
        return result
    assert queue("slots").stdout.strip() == "2"
    assert not (tmp_path / "work").exists()
    mb("prepare"); mb("plan")
    process = subprocess.Popen([sys.executable, "-m", "mockingbird.cli", "run",
                                "examples/capacity-gate.yaml"], cwd=tmp_path, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 8
        state = None
        while time.monotonic() < deadline:
            pointer = tmp_path / "work/capacity-gate/.reg/last_run.json"
            if pointer.exists():
                rd = Path(json.loads(pointer.read_text())["run_dir"])
                progress = rd / "progress.json"
                if progress.exists():
                    state = json.loads(progress.read_text())
                    if state['state'] == 'WAITING_CAPACITY': break
            assert process.poll() is None
            time.sleep(.02)
        assert state and state['state'] == 'WAITING_CAPACITY'
        assert state['job_id'] == 'sim_c' and process.poll() is None
        assert queue("slots").stdout.strip() == '0'
        records = json.loads((tmp_path / 'work/capacity-demo-queue/queue.json').read_text())
        assert [r['job_id'] for r in records] == ['sim_a', 'sim_b']
        run_id = rd.name
        # Submission also enforces the cap if someone bypasses the capacity query.
        queue("submit", expected=1, MB_RUN_ID=run_id, MB_JOB_ID='bypass')
        # A typo must not complete another requested Job partially.
        queue("finish", run_id, "sim_a", "missing", expected=1)
        assert queue("slots").stdout.strip() == '0'
        queue("finish", run_id, "sim_a")
        stdout, stderr = process.communicate(timeout=8)
        assert process.returncode == 0, stdout + stderr
        assert stdout.count('waiting for capacity') == 1
        records = json.loads((tmp_path / 'work/capacity-demo-queue/queue.json').read_text())
        assert [r['job_id'] for r in records] == ['sim_a', 'sim_b', 'sim_c']
        assert sum(r['state'] == 'ACTIVE' for r in records) == 2
        executions = (rd / 'executions.json').read_bytes()
        mb('collect', '--run-dir', str(rd), expected=2)
        result = json.loads((rd/'result.json').read_text())
        assert result['summary']['pass'] == 1 and result['summary']['pending'] == 2
        queue('finish', run_id, 'sim_b', 'sim_c')
        assert queue('slots').stdout.strip() == '2'
        mb('collect', '--run-dir', str(rd))
        result = json.loads((rd/'result.json').read_text())
        assert result['summary']['pass'] == 3 and result['summary']['pending'] == 0
        assert (rd/'executions.json').read_bytes() == executions
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)


def test_queue_reserves_capacity_across_simultaneous_submitters(tmp_path):
    env = environment(tmp_path)
    processes = [subprocess.Popen([sys.executable, 'examples/sample_queue.py', 'submit'],
                                  cwd=tmp_path, env=dict(env, MB_RUN_ID='shared', MB_JOB_ID=f'job{i}'),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(4)]
    try:
        for process in processes: process.communicate(timeout=5)
        assert sorted(p.returncode for p in processes) == [0, 0, 1, 1]
        records = json.loads((tmp_path/'work/capacity-demo-queue/queue.json').read_text())
        assert len(records) == 2 and all(r['state'] == 'ACTIVE' for r in records)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill(); process.communicate(timeout=5)
