from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import lifecycle
from .context import load_definition, prepare
from .doctor import doctor_failed, run_doctor
from .selection import Selection, write_selection_file
from .status import snapshot


def _add_selection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--failed-from",
        help="previous run directory or result.json; select tests whose status was FAIL",
    )
    parser.add_argument("--test", action="append", default=[], help="select exact job ID; repeatable")
    parser.add_argument("--match", action="append", default=[], help="select job ID glob; repeatable")
    parser.add_argument("--selection", help="text file containing selected job IDs")


def _selection(args) -> Selection:
    return Selection(
        failed_from=getattr(args, "failed_from", None),
        test_ids=list(getattr(args, "test", []) or []),
        patterns=list(getattr(args, "match", []) or []),
        selection_file=getattr(args, "selection", None),
    )


def _print_checklist(context: dict, selected, selection_meta: dict) -> None:
    scheduler = context["scheduler"]
    print("Run checklist")
    print(f"  [OK] context: {context['name']} @ {context['prepared_at']}")
    print(f"  [OK] workspace: {context['paths']['workspace']}")
    print(f"  [OK] sources: {len(context['sources'])}")
    for source in context["sources"]:
        print(
            f"       - {source['name']}: {source['resolved_revision']} "
            f"({source['provider']}, {source.get('materialization', 'prepared')}; prepare-time revision)"
        )
    print(
        f"  [OK] selection: {len(selected)} / {selection_meta['plan_count']} jobs"
    )
    if selection_meta.get("failed_from"):
        print(f"       failed-from: {selection_meta['failed_from']}")
    print(
        "  [OK] scheduler: "
        f"max_parallel={scheduler['max_parallel']}, "
        f"poll_interval_s={scheduler['poll_interval_s']}, "
        f"capacity={scheduler['capacity_provider']}"
    )
    print("  jobs:")
    preview_limit = 20
    for job in selected[:preview_limit]:
        print(f"       - {job.id}")
    if len(selected) > preview_limit:
        print(f"       ... {len(selected) - preview_limit} more (use mockingbird plan for full list)")


def _confirm() -> bool:
    answer = input("Proceed with this run? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def _summary(result: dict) -> str:
    return json.dumps(result["summary"], indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mockingbird")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("doctor", "prepare", "setup", "collect", "status", "all"):
        cmd = sub.add_parser(name)
        cmd.add_argument("definition")

    plan = sub.add_parser("plan")
    plan.add_argument("definition")
    plan.add_argument("--write-selection", metavar="PATH")

    dry = sub.add_parser("dry-run")
    dry.add_argument("definition")
    _add_selection_args(dry)

    run = sub.add_parser("run")
    run.add_argument("definition")
    _add_selection_args(run)
    run.add_argument("--interactive", action="store_true", help="show checklist and ask before run")

    collect = sub.choices["collect"]
    collect.add_argument("--run-dir")

    status = sub.choices["status"]
    status.add_argument("--run-dir")
    status.add_argument("--json", action="store_true", help="print the saved-state snapshot as JSON")

    all_cmd = sub.choices["all"]
    _add_selection_args(all_cmd)
    all_cmd.add_argument("--interactive", action="store_true")

    return parser


def _status(defn: dict, run_dir: str | None, as_json=False) -> None:
    data = snapshot(defn, run_dir)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(f"Run: {data['run_id']}")
    print(f"Execution (last recorded): {data['execution_status']}; {data['recorded']}/{data['total']} execution records")
    print(f"Last execution update: {data['last_execution_update']}")
    sweep = data['collection_sweep']
    phase = sweep.get('state', 'NOT_STARTED' if not any(j['observed_at'] for j in data['jobs']) else 'UNKNOWN')
    print(f"Collection: {data['final']}/{data['total']} final; sweep (last recorded): {phase}")
    counts = data['collection_counts']
    print(f"  pending={counts['PENDING']}, collection_error={counts['ERROR']}, uncollected={counts['UNCOLLECTED']}")
    if sweep:
        print(f"Last collection update: {sweep['updated_at']}")
    for job in data['jobs']:
        state = "COLLECTION_ERROR" if job['collection'] == "ERROR" else job['collection']
        verdict = job['verdict'] or "-"
        print(f"  {job['id']}: execution={job['execution']}; collection={state}; verdict={verdict}")
        if job['reason']:
            print(f"    Last collector report ({job['observed_at']}): {job['reason']}")
    print("Saved observations only; process liveness is not checked. Command completion does not imply external completion.")


def _progress(event, execution):
    text = {"WAITING_CAPACITY": "waiting for capacity", "EXECUTING": "executing",
            "COMMAND_FINISHED": "command finished"}[event['state']]
    if execution and isinstance(execution.observation, dict):
        observation = execution.observation
        if observation.get('timed_out'):
            text += " (timed out)"
        elif 'returncode' in observation:
            text += f" (exit={observation['returncode']})"
        elif 'launch_error' in observation or 'executor_error' in observation:
            text += " (execution error)"
    print(f"[{event['index']}/{event['total']}] {event['job_id']}: {text}", flush=True)


def _execution_summary(executions, run_dir):
    print(f"Execution finished: {len(executions)} execution records (external completion not checked)")
    print("Collection: not started")
    print(f"run: {run_dir}", flush=True)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    defn = load_definition(args.definition)

    if args.command == "doctor":
        checks = run_doctor(defn)
        for item in checks:
            print(f"{item.status:4}  {item.component:<24} {item.name:<20} {item.message}")
        if doctor_failed(checks):
            raise SystemExit(1)
        return

    if args.command == "prepare":
        print(json.dumps(prepare(defn), indent=2))
        return

    if args.command == "setup":
        lifecycle.setup(defn)
        print("setup: OK")
        return

    if args.command == "plan":
        plan = lifecycle.create_plan(defn)
        print(f"plan: {len(plan['jobs'])} jobs")
        for job in plan["jobs"]:
            print(f"  - {job['id']}")
        if args.write_selection:
            jobs = lifecycle.plan_jobs(defn)
            write_selection_file(args.write_selection, jobs)
            print(f"selection file: {Path(args.write_selection).resolve()}")
        return

    if args.command == "dry-run":
        context, selected, meta = lifecycle.preview(defn, _selection(args))
        _print_checklist(context, selected, meta)
        return

    if args.command == "run":
        selection = _selection(args)
        context, selected, meta = lifecycle.preview(defn, selection)
        if args.interactive:
            _print_checklist(context, selected, meta)
            if not _confirm():
                print("run: cancelled")
                return
        executions, run_dir, _ = lifecycle.run(defn, selection, on_progress=_progress)
        _execution_summary(executions, run_dir)
        return

    if args.command == "collect":
        print("Collection started", flush=True)
        result, run_dir = lifecycle.collect(defn, args.run_dir)
        print(_summary(result))
        print(f"run: {run_dir}")
        if result["status"] != "PASS":
            raise SystemExit(2 if result["status"] == "PENDING" else 1)
        return

    if args.command == "status":
        _status(defn, args.run_dir, args.json)
        return

    if args.command == "all":
        prepare(defn)
        lifecycle.setup(defn)
        lifecycle.create_plan(defn)
        selection = _selection(args)
        context, selected, meta = lifecycle.preview(defn, selection)
        if args.interactive:
            _print_checklist(context, selected, meta)
            if not _confirm():
                print("run: cancelled")
                return
        executions, run_dir, _ = lifecycle.run(defn, selection, on_progress=_progress)
        _execution_summary(executions, run_dir)
        print("Collection started", flush=True)
        result, _ = lifecycle.collect(defn, run_dir)
        print(_summary(result))
        print(f"run: {run_dir}")
        if result["status"] != "PASS":
            raise SystemExit(2 if result["status"] == "PENDING" else 1)
        return

    parser.error(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
