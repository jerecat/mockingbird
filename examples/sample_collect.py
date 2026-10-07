#!/usr/bin/env python3
"""User-owned collector: interpret project files and print one JSON object.

Mockingbird supplies MB_RUN_ID/MB_JOB_ID. The result directory, completion marker,
log syntax and artifact choices below are this sample project's conventions.
They are not rules imposed by Mockingbird. Diagnostic messages belong on stderr.
"""
import json
import os
import sys
from pathlib import Path


def collect(directory: Path) -> dict:
    result_file = directory / "result.txt"
    artifacts = [str((directory / name).resolve())
                 for name in ("result.txt", "tarmac.log", "wave.fsdb", "sim.log")
                 if (directory / name).is_file()]

    # A log can exist while execution is still running. Only the project-owned
    # completion marker says that it is ready for final judgement.
    if not (directory / "done").is_file():
        return {"status": "PENDING", "reason": "waiting for completion", "artifacts": artifacts}
    if not result_file.is_file():
        return {"status": "ERROR", "reason": "completed without result.txt", "artifacts": artifacts}
    verdict = result_file.read_text().strip()
    if verdict not in {"PASS", "FAIL", "ERROR", "SKIP"}:
        return {"status": "ERROR", "reason": "invalid verdict in result.txt", "artifacts": artifacts}
    reasons = {"FAIL": "mock scoreboard mismatch", "ERROR": "mock simulator fatal error",
               "SKIP": "mock unsupported configuration"}
    return {"status": verdict, "reason": reasons.get(verdict), "artifacts": artifacts}


if __name__ == "__main__":
    directory = (Path("work/sample-results") / os.environ["MB_RUN_ID"]
                 / os.environ["MB_JOB_ID"])
    # Demo instrumentation: inspect this to see which collectors were retried.
    if directory.is_dir():
        with (directory / "collector_calls.txt").open("a") as calls:
            calls.write("called\n")
    if (directory / "collector_unavailable").exists():
        print("MOCK result service unavailable", file=sys.stderr)
        sys.exit(7)
    if (directory / "collector_bad_json").exists():
        print("MOCK malformed response: not JSON")
        sys.exit(0)
    # PASS/FAIL/ERROR/PENDING are returned as JSON with exit code zero.
    # An unexpected exception exits nonzero: MB records a retryable collection
    # error, distinct from the final ERROR judgement returned above.
    print(json.dumps(collect(directory)))
