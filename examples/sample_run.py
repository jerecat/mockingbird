#!/usr/bin/env python3
"""Fake simv: create plain-text project artifacts, never judgement JSON."""
import os
from pathlib import Path


if __name__ == "__main__":
    job_id = os.environ["MB_JOB_ID"]
    directory = Path("work/sample-results") / os.environ["MB_RUN_ID"] / job_id
    directory.mkdir(parents=True, exist_ok=True)
    verdict = {"test_fail": "FAIL", "test_error": "ERROR", "test_skip": "SKIP"}.get(job_id, "PASS")
    (directory / "sim.log").write_text(f"MOCK simv +TEST={job_id}\nNo simulator was executed.\n")
    (directory / "tarmac.log").write_text("MOCK instruction trace: PC=0x1000 NOP\n")
    (directory / "wave.fsdb").write_text("MOCK ONLY: plain text, NOT a valid FSDB waveform.\n")
    (directory / "result.txt").write_text(verdict + "\n")
    if job_id == "test_collect_error":
        (directory / "collector_unavailable").touch()
    if job_id == "test_bad_json":
        (directory / "collector_bad_json").touch()
    # Pending models external work that has not completed yet. The finish helper
    # publishes its completion marker later, without another Mockingbird run.
    if job_id != "test_pending":
        (directory / "done").touch()
    print(f"MOCK simv: {job_id}; artifacts: {directory}")
    print("External completion pending" if job_id == "test_pending" else f"Project verdict: {verdict}")
    # Even FAIL/ERROR verdicts exit zero here, demonstrating that execution
    # return codes and collector judgements are separate concepts.
