from __future__ import annotations

import sys
import time
from pathlib import Path

from mockingbird.adapter_utils import run_process
from mockingbird.testing import make_execution_context


def test_process_output_is_streamed_to_files_not_returned_in_memory(tmp_path):
    execution = make_execution_context(tmp_path)
    marker = "x" * 1024
    result = run_process(
        [sys.executable, "-c", f"print({marker!r} * 1024)"],
        execution,
        timeout_s=5,
    )
    assert result.returncode == 0
    assert Path(result.stdout_path).stat().st_size > 1_000_000
    observation = result.to_observation()
    assert "stdout" not in observation
    assert "stderr" not in observation
    assert observation["stdout_path"] == result.stdout_path


def test_process_timeout_terminates_process_group(tmp_path):
    execution = make_execution_context(tmp_path)
    started = time.monotonic()
    result = run_process(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        execution,
        timeout_s=0.1,
        terminate_grace_s=0.1,
    )
    assert result.timed_out is True
    assert time.monotonic() - started < 2.0
    assert result.returncode != 0


def test_process_utility_rejects_empty_argv(tmp_path):
    execution = make_execution_context(tmp_path)
    import pytest
    with pytest.raises(ValueError, match="argv"):
        run_process([], execution)
