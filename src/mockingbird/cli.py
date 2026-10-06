from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import lifecycle
from .context import load_definition, metadata_path, prepare
from .doctor import doctor_failed, run_doctor
from .io import read_json
from .selection import Selection, write_selection_file


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
            f"({source['provider']})"
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

    all_cmd = sub.choices["all"]
    _add_selection_args(all_cmd)
    all_cmd.add_argument("--interactive", action="store_true")

    return parser


def _status(defn: dict, run_dir: str | None) -> None:
    if run_dir:
        path = Path(run_dir).resolve() / "result.json"
    else:
        pointer = metadata_path(defn) / "last_result.json"
        if not pointer.exists():
            raise RuntimeError("no collected result yet")
        path = Path(read_json(pointer)["result"])
    print(path.read_text(), end="")


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
        executions, run_dir, _ = lifecycle.run(defn, selection)
        print(f"executed: {len(executions)}")
        print(f"run: {run_dir}")
        return

    if args.command == "collect":
        result, run_dir = lifecycle.collect(defn, args.run_dir)
        print(_summary(result))
        print(f"run: {run_dir}")
        if result["status"] != "PASS":
            raise SystemExit(1)
        return

    if args.command == "status":
        _status(defn, args.run_dir)
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
        _, run_dir, _ = lifecycle.run(defn, selection)
        result, _ = lifecycle.collect(defn, run_dir)
        print(_summary(result))
        print(f"run: {run_dir}")
        if result["status"] != "PASS":
            raise SystemExit(1)
        return

    parser.error(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
