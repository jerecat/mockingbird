"""Guided CLI rehearsal in a new directory; never removes user files.

This UI driver invokes the public CLI, not alternate lifecycle implementations.
The existing example scripts remain the single source of tutorial behaviour.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

import yaml


EXAMPLES = ("sample-collector.yaml", "sample_run.py", "sample_collect.py", "sample_finish.py")
DEFINITION = "examples/sample-collector.yaml"


def _continue(automatic: bool) -> bool:
    if automatic:
        return True
    while True:
        try:
            answer = input("Enter to continue, q to stop: ").strip().lower()
        except EOFError:
            return False
        if answer in {"q", "quit"}:
            return False
        if not answer:
            return True
        print("Press Enter to execute this step, or type q to keep the files and stop.")


def _examples() -> Path:
    # Editable installation from the clone is the supported tutorial setup.
    source = Path(__file__).resolve().parents[2] / "examples"
    if not all((source / name).is_file() for name in EXAMPLES):
        raise ValueError("tutorial examples are unavailable; clone the Mockingbird repository "
                         "and install it with 'python -m pip install -e .'")
    return source


def _closing(root: Path, complete: bool) -> None:
    print("\nTutorial complete." if complete else "\nTutorial stopped; created files are kept.")
    print(f"Directory: {root}")
    print("Manual commands below assume this directory:")
    print(f"  {shlex.join(['cd', str(root)])}")
    print(f"  export MB_STATE_DIR={shlex.quote(str(root / '.mb-state'))}")
    print("Read GUIDE.md for the full sequence and how to continue.")
    print("MB context/plan: work/sample-collector/.reg/")
    print("MB records/logs: work/sample-collector/runs/<run-id>/")
    print("Project artifacts: work/sample-results/<run-id>/<job-id>/")
    print("\nOptional cleanup, only when you no longer need these files:")
    print(f"  {shlex.join(['cd', str(root.parent)])}")
    print(f"  {shlex.join(['rm', '-rf', '--', str(root)])}")
    print("This removes the tutorial directory, including any edits you made inside it.")
    print("Nothing is deleted automatically.")
    print("After manual work, unset MB_STATE_DIR (or restore its previous value).")


def run_tutorial(directory: str | None = None, automatic: bool = False, advanced: bool = False) -> None:
    source = _examples()
    print("Mockingbird guided tutorial")
    print("Advanced: includes failing verdicts and collector faults." if advanced else
          "Basics: run two Jobs, collect what is ready, then collect the remaining result.")
    count = "eight" if advanced else "two"
    print("The sample creates text artifacts; it does not run a simulator or clone sources.")
    print("All exercise files will live in a NEW directory. Existing directories are refused.")
    if directory:
        print(f"Requested directory: {Path(directory).absolute()}")
    else:
        print(f"A uniquely named mb-tutorial-* directory will be created under {Path.cwd()}.")
    if not _continue(automatic):
        print("Tutorial cancelled; no files created.")
        return
    if directory:
        root = Path(directory).absolute()
        # Do not resolve a final symlink: even dangling links must be refused.
        try:
            root.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            raise ValueError(f"tutorial directory already exists: {root}; choose a new directory "
                             "or use the existing exercise's GUIDE.md to continue") from None
    else:
        root = Path(tempfile.mkdtemp(prefix="mb-tutorial-", dir=Path.cwd()))
    complete = False
    try:
        (root / "examples").mkdir()
        for name in EXAMPLES:
            shutil.copyfile(source / name, root / "examples" / name)
        if not advanced:
            definition = root / DEFINITION
            data = yaml.safe_load(definition.read_text())
            data["execution"]["jobs"] = ["test_pass", "test_pending"]
            definition.write_text(yaml.safe_dump(data, sort_keys=False))
        (root / "GUIDE.md").write_text(_guide(advanced))
        env = dict(os.environ, MB_STATE_DIR=str(root / ".mb-state"))
        print(f"\nCreated: {root}")
        print(f"Commands run with cwd: {root}")
        print(f"Open examples/sample-collector.yaml to inspect the {count} Jobs.")
        print("plan: sample-collector keeps MB data under work/sample-collector/.")
        print("sources: [] uses existing scripts. Each run keeps its plan and records under runs/ there.")
        print("Each step below prints the ordinary command you can also run yourself.")
        print("This exercise has its own plan registry so repeated tutorials stay independent.")
        print(f"$ export MB_STATE_DIR={shlex.quote(env['MB_STATE_DIR'])}", flush=True)

        def step(title, explanation, args, expected=0, helper=False):
            print(f"\n--- {title} ---\n{explanation}")
            if helper:
                command = [sys.executable, *args]
                shown = command
            else:
                command = [sys.executable, "-m", "mockingbird.cli", *args]
                shown = ["mb", *args]
            print(f"$ {shlex.join(shown)}", flush=True)
            if not _continue(automatic):
                return False
            with subprocess.Popen(command, cwd=root, env=env) as process:
                try:
                    returncode = process.wait()
                except KeyboardInterrupt:
                    print("\nWaiting for the active CLI command to stop and save its records...", flush=True)
                    process.wait()
                    raise
            print(f"Exit code: {returncode} (expected {expected})", flush=True)
            if returncode != expected:
                raise RuntimeError("tutorial step failed; files were kept for inspection. "
                                   "Fix the reported error and use GUIDE.md to continue")
            return True

        print("This sample has no setup commands; prepare can go straight to plan.")
        stages = [
            ("1. Check connections", "Doctor checks configuration, executable availability and capacity without starting Jobs.\nThe summary groups these checks; use doctor --details if you need individual diagnostics.", ["doctor", DEFINITION]),
            ("2. Prepare", "Save context in work/sample-collector/.reg/. No source clone is needed.", ["prepare", DEFINITION]),
            ("3. Plan", f"Resolve defaults and validate {count} complete Job contracts; nothing executes yet.", ["plan", "sample-collector"]),
            ("4. Preview a selection", f"Preview test_pass and test_pending without executing them. The next run uses all {count} Jobs.",
             ["dry-run", "sample-collector", "--test", "test_pass", "--test", "test_pending"]),
            ("5. Run", f"Execute {count} commands serially. test_pending simulates external work that is still running.\nCommand completion does not mean that external work has finished.", ["run", "sample-collector"]),
            ("6. Status before collection", "Execution records exist; no results have been collected. Status reads saved observations, not liveness.", ["status", "sample-collector"]),
        ]
        for title, explanation, args in stages:
            if not step(title, explanation, args):
                return
        run_dir = Path(json.loads((root / "work/sample-collector/.reg/last_run.json").read_text())["run_dir"])
        collect = ["collect", "sample-collector", "--run-dir", str(run_dir)]
        status = ["status", "sample-collector", "--run-dir", str(run_dir), "--details"]
        first = ("Expected: PASS 2, FAIL 1, ERROR 1, SKIP 1, PENDING 1, collection errors 2.\n"
                 "No-check contributes a PASS without inspecting evidence. Exit 2 means unresolved results."
                 if advanced else
                 "test_pass is ready; test_pending is not finished yet.\n"
                 "Collect saves the ready result and leaves the other PENDING (exit 2).")
        if not step("7. Collect 1/2: get the results available now", first, collect, 2):
            return
        _check_results(run_dir, final=False, advanced=advanced)
        if advanced and not step("Inspect collector failures", "Final ERROR is a judgement. COLLECTION_ERROR means collection failed and can be retried.", status):
            return
        helper = ["examples/sample_finish.py", run_dir.name]
        if not advanced:
            helper.append("--pending-only")
        explanation = ("The sample helper marks the pending Job complete and removes collector fault markers."
                       if advanced else
                       "Imagine the external simulation has now finished. This SAMPLE helper creates its done file.\n"
                       "It does not run a simulation or repair MB. In real use, your external system finishes the work.")
        if not step("8. Make the remaining sample result available", explanation +
                    "\nThe done file is this sample's convention, not an MB requirement.", helper, helper=True):
            return
        second = ("Only the three unresolved Jobs are collected. Final counts: PASS 5, FAIL 1, ERROR 1, SKIP 1.\n"
                  "Exit 1 is intentional because final FAIL/ERROR verdicts remain."
                  if advanced else
                  "Collect the SAME run again: only test_pending needs a result.\n"
                  "test_pass stays final; neither Job is executed again. Expected: PASS 2 (exit 0).")
        if not step("9. Collect 2/2: get the remaining result", second, collect, 1 if advanced else 0):
            return
        _check_results(run_dir, final=True, advanced=advanced)
        if not step("10. Check that all results are final", f"All {count} results should now be final. No more collect is needed for this run.", status):
            return
        print("\nRun executes commands. Collect obtains results. If results are pending, collect the same run later.")
        if not advanced:
            print("Optional next exercise: mb tutorial --advanced (in a new directory).")
        complete = True
    finally:
        _closing(root, complete)


def _check_results(run_dir: Path, *, final: bool, advanced: bool = False) -> None:
    expected = {"total": 8, "pass": 5 if final else 2, "fail": 1, "error": 1,
                "skip": 1, "pending": 0 if final else 1, "uncollected": 0,
                "collection_error": 0 if final else 2}
    if not advanced:
        expected = {"total": 2, "pass": 2 if final else 1, "fail": 0, "error": 0,
                    "skip": 0, "pending": 0 if final else 1, "uncollected": 0, "collection_error": 0}
    result = json.loads((run_dir / "result.json").read_text())
    if result["summary"] != expected:
        raise RuntimeError(f"tutorial results differ from the expected sample: {result['summary']}; "
                           "inspect the kept files before continuing")


def _guide(advanced: bool = False) -> str:
    mode = "Advanced" if advanced else "Basic"
    first = ("PASS 2, FAIL 1, ERROR 1, SKIP 1, PENDING 1 and two collection errors."
             if advanced else "test_pass is PASS; test_pending is still PENDING.")
    helper = "" if advanced else " --pending-only"
    completion = ("The sample helper marks the pending Job complete and removes collector fault markers."
                  if advanced else "The sample helper creates test_pending's done file, standing in for external work finishing.")
    last = ("Only the three unresolved Jobs are collected. Final counts: PASS 5, FAIL 1, ERROR 1, SKIP 1.\n"
            "Exit 1 is intentional because FAIL/ERROR verdicts remain."
            if advanced else "Only test_pending is collected. test_pass stays final. Both Jobs are now PASS (exit 0).")
    return f"""# {mode} guided tutorial: manual continuation

Run commands from this exercise directory with the installed `mb` command.
First select this exercise's isolated plan registry (also printed by the guided command):

```sh
export MB_STATE_DIR="$PWD/.mb-state"
```

The examples create text artifacts, not real simulations. No external repository
is cloned. The basic exercise has two Jobs; --advanced uses all eight sample Jobs.

## Prepare and run

```sh
mb doctor examples/sample-collector.yaml
mb prepare examples/sample-collector.yaml
mb plan sample-collector
mb dry-run sample-collector --test test_pass --test test_pending
mb run sample-collector
mb status sample-collector
```

Run executes the commands. Command completion does not mean that external work
has finished. Use the run directory printed by run, replacing `<run-id>` below.

## Collect 1/2: get the results available now

```sh
mb collect sample-collector --run-dir work/sample-collector/runs/<run-id>
```

{first}
Exit 2 means results remain unresolved. Do not start another run to collect them.

## Make the remaining sample result available

```sh
python3 examples/sample_finish.py <run-id>{helper}
```

{completion}
This is a project sample helper, not an MB repair command. The done file is a
sample convention. In real use, your external system finishes the work.

## Collect 2/2: get the remaining result

```sh
mb collect sample-collector --run-dir work/sample-collector/runs/<run-id>
mb status sample-collector --run-dir work/sample-collector/runs/<run-id> --details
```

{last}
No Job is rerun. All results are final; no further collect is needed for this run.
Run executes commands; collect obtains results. If results are pending, collect
the same run later. Final results are retained.

## Continue after stopping

Execute the command shown at the paused step, then follow the remaining sequence.
Do not repeat earlier stages unnecessarily: prepare invalidates the saved plan and
run creates a NEW run. Use --run-dir for an existing run. If a step failed, fix
its error first. After interrupting run/collect, inspect status; unexecuted Jobs
cannot be collected. Invoking tutorial again creates a new exercise, not a resume.

## Paths and further exercises

- work/sample-collector/.reg/: MB context, plan, state and latest-run pointer.
- work/sample-collector/runs/<run-id>/: MB records, logs and result.json.
- work/sample-results/<run-id>/<job-id>/: project result.txt, sim.log, tarmac.log,
  mock wave.fsdb and collector_calls.txt (counts collection calls).
- examples/: editable copies of the YAML and scripts.

Commands use the invocation directory saved at prepare time as cwd. The sample
scripts locate their results using MB_RUN_ID and MB_JOB_ID. Editing YAML alone does not affect execution. Confirm execution edits with mb plan.
Preparation changes require prepare/setup before plan. Script contents remain user-managed.

Optional separate exercise: `mb tutorial --advanced` includes FAIL/ERROR/SKIP,
no-check and collector fault recovery. Both modes collect exactly twice.
To inspect JSON: `mb status sample-collector --json`.
For a smaller NEW run: `mb run sample-collector --test test_pass`.

## Cleanup is optional

Keep the directory as a reference. When finished, move to its parent and remove
ONLY this tutorial directory. The guided command prints the exact shell-quoted
rm command. Nothing is deleted automatically; deletion also removes your edits.
After cleanup, `unset MB_STATE_DIR` to return to your normal plan registry
(or restore its previous value if you had selected another registry).
"""
