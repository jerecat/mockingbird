#!/usr/bin/env python3
"""Find project results in this Job's execution stdout, without ID path guessing."""
import json
import os
from pathlib import Path


def collect():
    stdout = Path(os.environ["MB_STDOUT_PATH"])
    if not stdout.is_file():
        return {"status": "ERROR", "reason": "execution stdout is unavailable"}
    locations = {line.removeprefix("RESULT_DIR=") for line in stdout.read_text().splitlines()
                 if line.startswith("RESULT_DIR=")}
    if len(locations) != 1:
        return {"status": "ERROR", "reason": "expected exactly one RESULT_DIR in execution stdout"}
    directory = Path(locations.pop())
    if not directory.is_absolute():
        return {"status": "ERROR", "reason": "sample requires an absolute RESULT_DIR"}
    result = directory / "result.txt"
    if not result.is_file():
        return {"status": "PENDING", "reason": "waiting for project result.txt"}
    status = result.read_text().strip()
    if status not in {"PASS", "FAIL", "ERROR", "SKIP"}:
        return {"status": "ERROR", "reason": "invalid project verdict"}
    return {"status": status, "artifacts": [str(result)]}


if __name__ == "__main__":
    # Unexpected read/permission errors exit nonzero: retryable collection error.
    print(json.dumps(collect()))
