#!/usr/bin/env python3
"""Mock existing tool: prints its output location, with no MB dependencies."""
import tempfile
from pathlib import Path

root = Path("work/log-location-results")
root.mkdir(parents=True, exist_ok=True)
directory = Path(tempfile.mkdtemp(prefix="simulation-", dir=root)).resolve()
(directory / "result.txt").write_text("PASS\n")
print(f"RESULT_DIR={directory}", flush=True)
