from __future__ import annotations

import argparse
import json
import shlex
import sys
from contextlib import contextmanager, redirect_stdout
from threading import Event, Thread
from datetime import datetime

import yaml
from pathlib import Path

from . import lifecycle
from .context import load_definition, prepare, plan_target, metadata_path, run_root_path
from .errors import PrerequisiteError
from .doctor import doctor_failed, run_doctor
from .selection import Selection, write_selection_file
from .status import snapshot, history, plan_details
from .io import read_json
from .models import Job
from .setup_contract import setup_required
from . import registry


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
    print(f"  [OK] context: {context['plan']} @ {context['prepared_at']}")
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
    try:
        answer = input("Proceed with this run? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}



def _confirm_run(context, selected, selection_meta):
    _print_checklist(context, selected, selection_meta)
    return _confirm()


def _summary(result: dict) -> str:
    counts = result["summary"]
    verdicts = "  ".join(f"{key.upper()} {counts[key]}" for key in ("pass", "fail", "error", "skip"))
    unresolved = "  ".join(f"{key.replace('_', ' ')} {counts[key]}" for key in ("pending", "collection_error", "uncollected"))
    return f"Result: {result['status']} ({counts['total']} jobs)\n  {verdicts}\n  {unresolved}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mb", description="Run Jobs in list order and collect their results.",
        epilog="First run: prepare -> setup (if configured) -> plan -> run -> collect (or use all). "
               "Prepare registers the plan; named commands work from any directory.")
    parser.add_argument("--debug", action="store_true", help="show a traceback on errors")
    sub = parser.add_subparsers(dest="command", required=True)

    descriptions = {
        "doctor": "check configuration and plugin connections",
        "prepare": "prepare sources and save the workspace context",
        "setup": "set up the prepared execution environment",
        "collect": "collect saved executions, including during an active run",
        "status": "show saved observations for the latest-started run, or a selected run",
        "all": "prepare, setup, plan, run, then collect",
    }
    for name, description in descriptions.items():
        cmd = sub.add_parser(name, help=description, description=description)
        cmd.add_argument("definition", metavar="PLAN" if name in {"setup", "collect", "status"} else "YAML")

    plan = sub.add_parser("plan", help="validate and save the Job list")
    plan.add_argument("definition", metavar="PLAN")
    plan.add_argument("--write-selection", metavar="PATH")

    dry = sub.add_parser("dry-run", help="preview the planned selection without executing")
    dry.add_argument("definition", metavar="PLAN")
    _add_selection_args(dry)

    run = sub.add_parser("run", help="execute the prepared plan; does not collect results")
    run.add_argument("definition", metavar="PLAN")
    _add_selection_args(run)
    run.add_argument("--interactive", action="store_true", help="show checklist and ask before run")

    save = sub.add_parser("save", help="save a run's selected Jobs as a new plan YAML")
    save.add_argument("definition", metavar="PLAN")
    save.add_argument("--as", dest="new_name", required=True, metavar="NEW_PLAN")
    save.add_argument("--output", required=True, metavar="YAML")
    save.add_argument("--run", help="run ID; defaults to latest-started run")
    save.add_argument("--test", action="append", dest="test_ids", help="Job ID from this run; repeatable")

    collect = sub.choices["collect"]
    collect.add_argument("--refresh", action="store_true",
                         help="debug/repair collectors: re-collect with confirmed collect-only changes")
    collect_run = collect.add_mutually_exclusive_group()
    collect_run.add_argument("--run-dir", help="explicit run directory (including old runs)")
    collect_run.add_argument("--run", help="run ID within this plan")

    status = sub.choices["status"]
    status_run = status.add_mutually_exclusive_group()
    status_run.add_argument("--run-dir", help="explicit run directory (including old runs)")
    status_run.add_argument("--run", help="run ID within this plan")
    status_view = status.add_mutually_exclusive_group()
    status_view.add_argument("--history", action="store_true", help="list this plan's runs and results")
    status_view.add_argument("--plan", action="store_true", help="show the confirmed plan, or the plan saved in --run")
    status.add_argument("--json", action="store_true", help="print the saved-state snapshot as JSON")

    all_cmd = sub.choices["all"]
    _add_selection_args(all_cmd)
    all_cmd.add_argument("--interactive", action="store_true")
    for cmd in (run, all_cmd):
        cmd.add_argument("--skip-source-check", action="store_true",
                         help="skip run-start source observations; record source state as unknown")

    sub.choices["doctor"].add_argument("--details", action="store_true", help="show every diagnostic check")
    status.add_argument("--details", action="store_true", help="include collector reasons and observation times")
    for name in ("prepare", "collect"):
        sub.choices[name].add_argument("--json", action="store_true", help="print JSON instead of the human summary")
    tutorial = sub.add_parser("tutorial", help="walk through the mock simulation in a new directory")
    tutorial.add_argument("--directory", help="new exercise directory (must not already exist)")
    tutorial.add_argument("--advanced", action="store_true", help="include final failure verdicts and collector fault recovery")
    tutorial.add_argument("--yes", action="store_true", help="run all tutorial steps without pausing")
    for cmd in sub.choices.values():
        cmd.add_argument("--debug", action="store_true", default=argparse.SUPPRESS,
                         help="show a traceback on errors")
    return parser


def _command(command, definition, run_dir=None):
    parts = ["mb", command, str(definition)]
    if run_dir is not None:
        parts.extend(["--run-dir", str(run_dir)])
    return shlex.join(parts)


def _next(command, definition, run_dir=None):
    print(f"Next: {_command(command, definition, run_dir)}")


def _definition_for(defn):
    defn = registry.definition_target(defn)
    path = metadata_path(defn) / "context.json"
    if path.is_file():
        return read_json(path).get("definition_path", "<definition.yaml>")
    entry = registry.lookup(defn['plan'])
    return entry['definition_path'] if entry else "<definition.yaml>"


def _history(defn, as_json=False):
    data = history(defn)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(f"Plan: {data['plan']}")
    if not data['runs']:
        print("No runs yet.")
        return
    rows = [("RUN", "EXECUTION", "RESULT", "JOBS")]
    rows += [(r['run_id'], r['execution'], r['result'] or "UNCOLLECTED", str(r['jobs'])) for r in data['runs']]
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    for row in rows:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)).rstrip())
    print(f"Inspect: mb status {defn['plan']} --run <run-id>")
    print(f"Saved plan: mb status {defn['plan']} --run <run-id> --plan")


def _time(value):
    if not value:
        return "-"
    return datetime.fromisoformat(value).astimezone().isoformat(sep=" ", timespec="seconds")


def _status(defn: dict, run_dir: str | None, as_json=False, details=False) -> None:
    data = snapshot(defn, run_dir)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(f"Run:        {data['run_id']}")
    print(f"Execution:  {data['execution_status']} ({data['recorded']}/{data['total']} records)")
    print(f"Updated:    {_time(data['last_execution_update'])}")
    sweep = data['collection_sweep']
    phase = sweep.get('state', 'NOT_STARTED' if not any(j['observed_at'] for j in data['jobs']) else 'UNKNOWN')
    print(f"Collection: {data['final']}/{data['total']} final; sweep {phase}")
    counts = data['collection_counts']
    print(f"            pending {counts['PENDING']}  collection errors {counts['ERROR']}  uncollected {counts['UNCOLLECTED']}")
    if sweep:
        print(f"Updated:    {_time(sweep['updated_at'])}")
    rows = [("JOB", "EXECUTION", "COLLECTION", "RESULT")]
    rows.extend((job['id'], job['execution'],
                 "COLLECTION_ERROR" if job['collection'] == "ERROR" else job['collection'],
                 job['verdict'] or "-") for job in data['jobs'])
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    print()
    for row in rows:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip())
    reasons = [job for job in data['jobs'] if job['reason']]
    if details:
        for job in reasons:
            print(f"\n{job['id']} — Last collector report ({_time(job['observed_at'])}):")
            for line in job['reason'].splitlines():
                print(f"  {line}")
    elif reasons:
        print("\nUse --details for collector reasons and observation times.")
    print("\nLast recorded states; process liveness is not checked.")
    print("Command completion does not imply external completion.")
    print(f"run: {data['run_dir']}")
    if data['final'] < data['recorded']:
        _next("collect", defn['plan'], data['run_dir'])
    if data['recorded'] < data['total'] and data['execution_status'] != "RUNNING":
        print("Jobs without execution records cannot be collected; run starts a new run.")


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
    if execution and isinstance(execution.observation, dict):
        observation = execution.observation
        error = observation.get("launch_error") or observation.get("executor_error")
        failed = error or observation.get("timed_out") or observation.get("returncode", 0) != 0
        if error:
            print(f"  {error}", flush=True)
        if failed:
            paths = observation.get("execution_context", {})
            if paths.get("job_dir"):
                print(f"  Record: {Path(paths['job_dir']) / 'execution.json'}", flush=True)
            if paths.get("stderr_path"):
                print(f"  Stderr: {paths['stderr_path']}", flush=True)



SOURCE_PROGRESS_INTERVAL_S = 0.4
SOURCE_PROGRESS_MAX_DOTS = 6


@contextmanager
def _source_check():
    stream = sys.stdout
    animated = stream.isatty()
    stop = Event()
    print("Checking sources...", end="" if animated else "\n", file=stream, flush=True)

    def animate():
        dots = 3
        while not stop.wait(SOURCE_PROGRESS_INTERVAL_S):
            dots = dots % SOURCE_PROGRESS_MAX_DOTS + 1
            print("\rChecking sources" + "." * dots + " " * (SOURCE_PROGRESS_MAX_DOTS - dots),
                  end="", file=stream, flush=True)

    worker = Thread(target=animate, daemon=True) if animated else None
    try:
        if worker:
            worker.start()
        yield
    finally:
        stop.set()
        if worker:
            worker.join()
            print(file=stream, flush=True)


def _source_skipped(observations):
    print("Sources: skipped (--skip-source-check)", flush=True)


def _source_summary(observations):
    dirty = sum(item.get("tracked_dirty", item.get("dirty")) is True
                for item in observations.values())
    unknown = sum(item.get("tracked_dirty", item.get("dirty")) is None
                  for item in observations.values())
    print(f"Sources: {len(observations)} checked, {dirty} tracked-dirty, {unknown} unknown", flush=True)
    for name, item in observations.items():
        if item.get("error"):
            print(f"  {name}: {item['error']}", flush=True)


def _setup_progress(index, total, job_id, state):
    print(f"Setup [{index}/{total}] {job_id}: {state}", flush=True)


def _execution_summary(executions, run_dir):
    print(f"Execution finished: {len(executions)} execution records (external completion not checked)")
    print("Collection: use status to inspect saved results")
    print(f"run: {run_dir}", flush=True)


def _doctor_summary(checks, details=False):
    attention = [item for item in checks if item.status.upper() != "PASS"]
    outcome = "FAILED" if doctor_failed(checks) else "ATTENTION" if attention else "OK"
    print(f"Pre-run checks: {outcome}")
    labels = {"configuration": "Definition", "execution": "Execution and collection",
              "capacity": "Execution capacity", "setup": "Preparation commands"}
    groups = {}
    for item in checks:
        groups.setdefault(item.component, []).append(item)
    rows = []
    for component, items in groups.items():
        label = labels.get(component, "Source " + component[7:] if component.startswith("source:") else component)
        state = "FAILED" if doctor_failed(items) else "ATTENTION" if any(i.status.upper() != "PASS" for i in items) else "OK"
        fixed = next((i for i in items if component == "capacity" and i.name == "fixed"
                      and i.status.upper() == "PASS" and "available_slots" in i.details), None)
        if fixed:
            slots = fixed.details["available_slots"]
            state += f" ({slots} configured slot{'s' if slots != 1 else ''})"
            if slots == 0:
                state += "; dispatch will wait"
        rows.append((label, state))
    width = max((len(label) for label, _ in rows), default=0)
    for label, state in rows:
        print(f"  {label + ':':<{width + 1}} {state}")
    if any(i.component == "configuration" and i.status.upper() == "PASS" for i in checks):
        print("  Run order: one Job at a time, in list order.")
    print("No Jobs executed. These checks do not guarantee a successful run.")
    if details:
        print("\nDiagnostic checks:")
        rows = [("STATUS", "COMPONENT", "CHECK", "MESSAGE")]
        rows.extend((i.status, i.component, i.name, i.message) for i in checks)
        widths = [max(len(row[n]) for row in rows) for n in range(3)]
        for row in rows:
            prefix = "  ".join(value.ljust(width) for value, width in zip(row[:3], widths)) + "  "
            lines = row[3].splitlines() or [""]
            print(prefix + lines[0])
            for line in lines[1:]:
                print(" " * len(prefix) + line)
    elif attention:
        print("\nNeeds attention:")
        for item in attention:
            name = "loading" if item.name == "plugin" else item.name
            print(f"  {item.status} {item.component} / {name}:")
            for line in item.message.splitlines():
                print(f"    {line}")
    if not details:
        print("Use --details for individual checks and executable paths.")
    if doctor_failed(checks):
        print("Fix the reported issues, then run doctor again.")


def _dispatch(args, parser) -> None:
    if args.command == "tutorial":
        from .tutorial import run_tutorial
        run_tutorial(args.directory, args.yes, args.advanced)
        return
    named = args.command in {"setup", "plan", "run", "dry-run", "collect", "status", "save"}
    if named:
        # Explicit run paths can refer to another operator's or legacy evidence;
        # inspecting them must neither require nor change our name registration.
        defn = (plan_target(args.definition, Path.cwd()) if getattr(args, "run_dir", None)
                else plan_target(args.definition))
    else:
        defn = load_definition(args.definition)
    args.plan_name = defn.get("plan")
    if args.command == "plan":
        definition_path = _definition_for(defn)
        loaded = load_definition(definition_path)
        if loaded.get("plan") != args.plan_name:
            raise ValueError(f"registered YAML {definition_path} must contain plan: {args.plan_name}")
        defn = dict(loaded, _invocation_dir=defn["_invocation_dir"])
    if getattr(args, "run", None):
        run_id = args.run
        if Path(run_id).name != run_id or run_id in {".", ".."} or "\\" in run_id:
            raise ValueError("--run must be a run ID, not a path; use --run-dir for a path")
        args.run_dir = str(run_root_path(defn) / run_id)

    if args.command == "save":
        from .save import save_plan
        result = save_plan(defn, args.new_name, args.output,
                           run_dir=getattr(args, "run_dir", None), test_ids=args.test_ids)
        print(f"Source run: {result['run_id']}")
        print(f"Jobs: {result['jobs']}")
        print(f"Created: {args.output}")
        print(f"Plan: {args.new_name}")
        for warning in result['warnings']:
            print(f"Warning: {warning}", file=sys.stderr)
        _next("prepare", args.output)
        return

    if args.command == "doctor":
        checks = run_doctor(defn)
        _doctor_summary(checks, args.details)
        if doctor_failed(checks):
            raise SystemExit(1)
        return

    if args.command == "prepare":
        if args.json:
            with redirect_stdout(sys.stderr):
                context = prepare(defn)
            print(json.dumps(context, indent=2))
        else:
            print("Preparing workspace...", flush=True)
            context = prepare(defn)
            print(f"Prepared: {context['plan']}")
            print(f"Workspace: {context['paths']['workspace']}")
            print(f"Sources: {len(context['sources'])}")
            for source in context['sources']:
                print(f"  {source['name']}: {source.get('materialization', 'prepared')}")
            _next("setup" if setup_required(context) else "plan", defn["plan"])
        return

    if args.command == "setup":
        print("Setting up execution environment...", flush=True)
        attempt = lifecycle.setup(defn, on_progress=_setup_progress)
        if attempt:
            print(f"Setup complete. Records: {attempt}")
        else:
            print("Setup not required: no setup commands configured.")
        _next("plan", defn["plan"])
        return

    if args.command == "plan":
        print("Validating plan...", flush=True)
        plan = lifecycle.create_plan(defn)
        args.plan_confirmed = True
        print(f"Confirmed: {defn['plan']} ({len(plan['jobs'])} jobs)")
        for job in plan["jobs"]:
            print(f"  - {job['id']}")
        if args.write_selection:
            jobs = [Job(**item) for item in plan["jobs"]]
            write_selection_file(args.write_selection, jobs)
            print(f"selection file: {Path(args.write_selection).resolve()}")
        _next("run", defn["plan"])
        return

    if args.command == "dry-run":
        context, selected, meta = lifecycle.preview(defn, _selection(args))
        _print_checklist(context, selected, meta)
        return

    if args.command == "run":
        selection = _selection(args)
        outcome = lifecycle.run(defn, selection, on_progress=_progress, on_sources=_source_skipped if args.skip_source_check else _source_summary,
                                source_check=_source_check, skip_source_check=args.skip_source_check,
                                confirm=_confirm_run if args.interactive else None)
        if outcome is None:
            print("run: cancelled; no Jobs started")
            return
        executions, run_dir, _ = outcome
        _execution_summary(executions, run_dir)
        _next("collect", defn["plan"], run_dir)
        return

    if args.command == "collect":
        if args.json:
            with redirect_stdout(sys.stderr):
                result, run_dir = lifecycle.collect(defn, args.run_dir, refresh=args.refresh)
            print(json.dumps(result, indent=2))
        else:
            print("Checking collector refresh..." if args.refresh else "Collection started", flush=True)
            result, run_dir = lifecycle.collect(defn, args.run_dir, refresh=args.refresh)
            _collection_summary(result, run_dir, defn["plan"])
        if result["status"] != "PASS":
            raise SystemExit(2 if result["status"] == "PENDING" else 1)
        return

    if args.command == "status":
        if args.history:
            if args.run_dir:
                raise ValueError("--history lists all runs; use --run or --run-dir without --history")
            _history(defn, args.json)
        elif args.plan:
            data = plan_details(defn, args.run_dir)
            print(json.dumps(data, indent=2))
        else:
            _status(defn, args.run_dir, args.json, args.details)
        return

    if args.command == "all":
        print("Preparing workspace...", flush=True)
        context = prepare(defn)
        defn = dict(defn, _invocation_dir=context["invocation_dir"])
        if setup_required(context):
            print("Setting up execution environment...", flush=True)
            lifecycle.setup(defn, on_progress=_setup_progress)
        print("Validating plan...", flush=True)
        lifecycle.create_plan(defn)
        selection = _selection(args)
        outcome = lifecycle.run(defn, selection, on_progress=_progress, on_sources=_source_skipped if args.skip_source_check else _source_summary,
                                source_check=_source_check, skip_source_check=args.skip_source_check,
                                confirm=_confirm_run if args.interactive else None)
        if outcome is None:
            print("run: cancelled; no Jobs started")
            return
        executions, run_dir, _ = outcome
        _execution_summary(executions, run_dir)
        print("Collection started", flush=True)
        result, _ = lifecycle.collect(defn, run_dir)
        _collection_summary(result, run_dir, defn["plan"])
        if result["status"] != "PASS":
            raise SystemExit(2 if result["status"] == "PENDING" else 1)
        return

    parser.error(f"unsupported command: {args.command}")


def _collection_summary(result, run_dir, definition):
    print(_summary(result))
    print(f"run: {run_dir}")
    if result["status"] != "PASS":
        print(f"Inspect: {_command('status', definition, run_dir)} --details")
    if result['summary']['pending'] or result['summary']['collection_error']:
        print("Collect again after external work finishes or collector errors are resolved.")
    if result['summary']['uncollected']:
        print("Jobs without execution records remain uncollected. If run is still active, "
              "collect again as records arrive. Otherwise, run starts a new run.")
    if any(result['summary'][key] for key in ('pending', 'collection_error', 'uncollected')):
        _next("collect", definition, run_dir)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        _dispatch(args, parser)
    except KeyboardInterrupt:
        if args.debug:
            raise
        print("Interrupted.", file=sys.stderr)
        if args.command in {"run", "collect", "all"}:
            print("Inspect saved state before retrying (if a run was created):", file=sys.stderr)
            print(f"  {_command('status', getattr(args, 'plan_name', None) or args.definition, getattr(args, 'run_dir', None))}", file=sys.stderr)
        else:
            print("The operation did not complete; retry it when ready.", file=sys.stderr)
        raise SystemExit(130) from None
    except Exception as exc:
        if args.debug:
            raise
        message = str(exc) or type(exc).__name__
        print(f"Error: {message}", file=sys.stderr)
        if isinstance(exc, PrerequisiteError):
            print("Required steps:", file=sys.stderr)
            for step in exc.steps:
                if step == args.command:
                    break
                target = (getattr(args, "plan_name", None) or args.definition) if step in {"setup", "plan", "run"} else (
                    args.definition if args.command in {"prepare", "all", "doctor"} else
                    _definition_for(plan_target(args.definition)))
                print(f"  {_command(step, target)}", file=sys.stderr)
            print("Then retry your command.", file=sys.stderr)
        if args.command == "plan":
            if getattr(args, "plan_confirmed", False):
                print("Plan was confirmed, but follow-up output failed; inspect it with "
                      f"mb status {args.plan_name} --plan.", file=sys.stderr)
            else:
                print("Plan confirmation failed; the last successfully confirmed plan was not replaced.", file=sys.stderr)
        if not isinstance(exc, (PrerequisiteError, ValueError, OSError, yaml.YAMLError)):
            print("Use --debug for a traceback.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
