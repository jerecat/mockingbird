"""Guided CLI rehearsal in a new directory; never removes user files.

This UI driver invokes the public CLI, not alternate lifecycle implementations.
The existing example scripts remain the single source of tutorial behaviour.
"""
from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


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
    print("Read GUIDE.md for the full sequence and how to continue.")
    print("MB context/plan: work/sample-collector/.reg/")
    print("MB records/logs: runs/sample-collector/<run-id>/")
    print("Project artifacts: work/sample-results/<run-id>/<job-id>/")
    print("\nOptional cleanup, only when you no longer need these files:")
    print(f"  {shlex.join(['cd', str(root.parent)])}")
    print(f"  {shlex.join(['rm', '-rf', '--', str(root)])}")
    print("This removes the tutorial directory, including any edits you made inside it.")
    print("Nothing is deleted automatically.")


def run_tutorial(directory: str | None = None, automatic: bool = False) -> None:
    source = _examples()
    print("Mockingbird guided tutorial")
    print("Try prepare, setup, plan, selection, run, status, collect and recovery.")
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
        (root / "GUIDE.md").write_text(_guide())
        print(f"\nCreated: {root}")
        print(f"Commands run with cwd: {root}")
        print("Open examples/sample-collector.yaml to inspect the eight Jobs.")
        print("sources: [] uses existing scripts. workspace holds preparation metadata;")
        print("run_root holds run records. The scripts choose their own artifact directory.")
        print("Each step below prints the ordinary command you can also run yourself.")

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
            with subprocess.Popen(command, cwd=root) as process:
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

        stages = [
            ("1. Check connections", "Doctor checks configuration, executable availability and capacity without starting Jobs.\nThe summary groups these checks; use doctor --details if you need individual diagnostics.", ["doctor", DEFINITION]),
            ("2. Prepare", "Save context in work/sample-collector/.reg/. No source clone is needed.", ["prepare", DEFINITION]),
            ("3. Setup", "Prepare the adapter environment. This sample needs no project build.", ["setup", DEFINITION]),
            ("4. Plan", "Resolve defaults and validate eight complete Job contracts; nothing executes yet.", ["plan", DEFINITION]),
            ("5. Preview a selection", "Select two Jobs without executing them. The next run will use all eight.",
             ["dry-run", DEFINITION, "--test", "test_pass", "--test", "test_pending"]),
            ("6. Run", "Execute eight commands serially. Exit zero records command completion, not a PASS verdict.", ["run", DEFINITION]),
            ("7. Status before collection", "Execution records exist; no results have been collected. Status reads saved observations, not liveness.", ["status", DEFINITION]),
        ]
        for title, explanation, args in stages:
            if not step(title, explanation, args):
                return
        run_dir = Path(json.loads((root / "work/sample-collector/.reg/last_run.json").read_text())["run_dir"])
        collect = ["collect", DEFINITION, "--run-dir", str(run_dir)]
        status = ["status", DEFINITION, "--run-dir", str(run_dir), "--details"]
        if not step("8. Collect", "Expected: PASS 2, FAIL 1, ERROR 1, SKIP 1, PENDING 1, collection errors 2.\n"
                    "No-check contributes a PASS without inspecting evidence. Exit 2 means unresolved results.", collect, 2):
            return
        _check_results(run_dir, final=False)
        if not step("9. Inspect reasons", "Final ERROR is a judgement. COLLECTION_ERROR means collection failed and can be retried.", status):
            return
        if not step("10. Simulate external completion", "This project helper creates the pending Job's done marker and removes collector fault markers.\n"
                    "The done file is a sample convention, not an MB contract. No Jobs are rerun.",
                    ["examples/sample_finish.py", run_dir.name], helper=True):
            return
        if not step("11. Collect unresolved Jobs", "Only the three unresolved Jobs are recollected. Expected: PASS 5, FAIL 1, ERROR 1, SKIP 1.\n"
                    "Exit 1 is intentional: all results are final, but the sample contains FAIL/ERROR verdicts.", collect, 1):
            return
        _check_results(run_dir, final=True)
        if not step("12. Inspect final results", "All eight results are final. Artifact paths are in result.json; files stay where the project wrote them.", status):
            return
        if not step("13. Collect once more", "Final results are retained. No collectors should run again; collector_calls.txt in each project directory records calls.", collect, 1):
            return
        _check_results(run_dir, final=True)
        complete = True
    finally:
        _closing(root, complete)


def _check_results(run_dir: Path, *, final: bool) -> None:
    expected = {"total": 8, "pass": 5 if final else 2, "fail": 1, "error": 1,
                "skip": 1, "pending": 0 if final else 1, "uncollected": 0,
                "collection_error": 0 if final else 2}
    result = json.loads((run_dir / "result.json").read_text())
    if result["summary"] != expected:
        raise RuntimeError(f"tutorial results differ from the expected sample: {result['summary']}; "
                           "inspect the kept files before continuing")


def _guide() -> str:
    return """# Guided tutorial: manual continuation

Run these commands from this directory with the installed `mb` command.
This directory contains copies of the repository's mock simulation examples.
No simulator or external Git repository is used. Every wave.fsdb is mock text.

```sh
mb doctor examples/sample-collector.yaml
mb prepare examples/sample-collector.yaml
mb setup examples/sample-collector.yaml
mb plan examples/sample-collector.yaml
mb dry-run examples/sample-collector.yaml --test test_pass --test test_pending
mb run examples/sample-collector.yaml
mb status examples/sample-collector.yaml
mb collect examples/sample-collector.yaml
mb status examples/sample-collector.yaml --details
```

The first collect exits 2 (PENDING): PASS 2, FAIL 1, ERROR 1, SKIP 1,
PENDING 1 and two collection errors. This is intentional.

Use the run directory printed by run, replacing `<run-id>` below:

```sh
python3 examples/sample_finish.py <run-id>
mb collect examples/sample-collector.yaml --run-dir runs/sample-collector/<run-id>
mb status examples/sample-collector.yaml --run-dir runs/sample-collector/<run-id> --details
mb collect examples/sample-collector.yaml --run-dir runs/sample-collector/<run-id>
```

Both later collects exit 1: all eight results are final but FAIL/ERROR remain.
The second collect retries only unresolved Jobs; the third invokes no collectors.
Final counts: PASS 5, FAIL 1, ERROR 1, SKIP 1. Inspect each project's
collector_calls.txt to see which collectors ran. No-check never calls a collector.

## Continue after stopping

Execute the command shown at the paused step, then follow the remaining sequence.
Do not rerun earlier commands unnecessarily: prepare invalidates setup/plan,
and run creates a NEW run. Use --run-dir to inspect or collect an existing run.
If a step failed, resolve its reported error before continuing. After interrupting
run/collect, inspect status first; Jobs never executed cannot be collected.
Invoking mb tutorial again creates another exercise; it does not resume this one.

## Paths and changes

- work/sample-collector/.reg/: MB context, plan, state and latest-run pointer.
- runs/sample-collector/<run-id>/: MB records, logs and result.json.
- work/sample-results/<run-id>/<job-id>/: project result.txt, sim.log, tarmac.log,
  mock wave.fsdb and collector call counts.
- examples/: editable copies of the sample YAML and scripts.

Commands use the invocation directory recorded at prepare time as cwd.
The sample scripts choose their result location using MB_RUN_ID and MB_JOB_ID.
Changing YAML requires prepare/setup/plan again; saved contracts do not snapshot
script contents. Keep run and collector paths pointed at the same project.

To try a smaller new run: mb run examples/sample-collector.yaml --test test_pass.
To inspect machine-readable state: mb status examples/sample-collector.yaml --json.
For a one-shot fresh lifecycle: mb all examples/sample-collector.yaml (exit 2 is
expected until the new run's pending results are resolved).

## Cleanup is optional

Keep this entire directory to inspect or edit the exercise. When finished, move
to its parent and remove ONLY this tutorial directory. The guided command prints
its exact shell-quoted rm command. Nothing is removed automatically, and removing
the directory also removes any edits made inside it.
"""
