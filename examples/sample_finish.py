#!/usr/bin/env python3
"""Simulate external completion and service recovery; does not edit MB records."""
import argparse
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="run directory basename printed by mb run")
    parser.add_argument("--pending-only", action="store_true", help="complete only the pending sample Job; do not simulate collector repair")
    args = parser.parse_args()
    if Path(args.run_id).name != args.run_id or args.run_id in {".", ".."}:
        parser.error("run_id must be one directory name")
    root = Path("work/sample-results") / args.run_id
    jobs = ("test_pending",) if args.pending_only else ("test_pending", "test_collect_error", "test_bad_json")
    for job in jobs:
        if not (root / job / "result.txt").is_file():
            parser.error(f"sample output missing: {root / job}; run the sample first")
    (root / "test_pending" / "done").touch()
    if args.pending_only:
        print(f"MOCK external Job completed: test_pending ({args.run_id})")
        raise SystemExit(0)
    (root / "test_collect_error" / "collector_unavailable").unlink(missing_ok=True)
    (root / "test_bad_json" / "collector_bad_json").unlink(missing_ok=True)
    print(f"MOCK external completion and collector recovery: {args.run_id}")
