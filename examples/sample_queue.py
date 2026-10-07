#!/usr/bin/env python3
"""A file-backed external queue with two slots; no simulations are launched.

Submission reserves a slot before returning. Manual completion releases it.
Run every command from the same invocation directory as MB. Queue state is
project-owned and intentionally independent of Mockingbird execution records.
"""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile

LIMIT = 2
ROOT = Path("work/capacity-demo-queue")


@contextmanager
def queue(*, write=False):
    if not write and not ROOT.exists():
        yield []
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / "queue.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = ROOT / "queue.json"
        records = json.loads(path.read_text()) if path.exists() else []
        yield records
        if write:
            with tempfile.NamedTemporaryFile(mode="w", dir=ROOT, delete=False) as output:
                temporary = Path(output.name)
                json.dump(records, output, indent=2)
                output.write("\n")
            try:
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)


def active(records):
    return sum(record["state"] == "ACTIVE" for record in records)


def identity():
    return os.environ["MB_RUN_ID"], os.environ["MB_JOB_ID"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("slots", "submit", "collect", "status"):
        sub.add_parser(command)
    finish = sub.add_parser("finish")
    finish.add_argument("run_id")
    finish.add_argument("jobs", nargs="+", help="Job IDs to mark complete")
    args = parser.parse_args()
    try:
        with queue(write=args.command in {"submit", "finish"}) as records:
            if args.command == "slots":
                # Protocol: stdout must be exactly one non-negative integer.
                print(max(0, LIMIT - active(records)))
            elif args.command == "status":
                print(f"External queue (MOCK): {active(records)}/{LIMIT} slots occupied")
                print("ACTIVE includes submitted work, whether queued or running.")
                for record in records:
                    print(f"{record['run_id']}  {record['job_id']:<8} {record['state']}")
            elif args.command == "submit":
                run_id, job_id = identity()
                existing = next((r for r in records if (r['run_id'], r['job_id']) == (run_id, job_id)), None)
                if existing is None:
                    if active(records) >= LIMIT:
                        raise ValueError("external queue is full; submission refused")
                    records.append({"run_id": run_id, "job_id": job_id, "state": "ACTIVE"})
                print(f"MOCK submitted {run_id}/{job_id}; command returns before external completion")
                # The transaction commits before this process exits. A subsequent
                # slots query therefore counts this submission immediately.
            elif args.command == "finish":
                selected = [next((r for r in records if r['run_id'] == args.run_id and r['job_id'] == job), None)
                            for job in args.jobs]
                if any(record is None for record in selected):
                    raise ValueError("a requested Job has not been submitted; inspect queue status first")
                for record in selected:
                    record['state'] = 'DONE'
                print(f"MOCK completed: {args.run_id} / {', '.join(args.jobs)}")
            elif args.command == "collect":
                run_id, job_id = identity()
                record = next((r for r in records if (r['run_id'], r['job_id']) == (run_id, job_id)), None)
                if record is None:
                    outcome = {"status": "ERROR", "reason": "no submission recorded in the sample queue"}
                elif record['state'] == 'ACTIVE':
                    outcome = {"status": "PENDING", "reason": "external work is submitted but not complete"}
                else:
                    outcome = {"status": "PASS"}
                print(json.dumps(outcome))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Sample queue error: {exc}\n")


if __name__ == "__main__":
    main()
