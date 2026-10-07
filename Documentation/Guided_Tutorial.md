# Guided terminal tutorial

Clone Mockingbird and install it once:

```sh
git clone https://github.com/jerecat/mockingbird.git
cd mockingbird
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
mb tutorial
```

The guided command needs the examples in this editable repository checkout.
A standalone wheel installation without the checkout does not include them;
the command explains how to obtain the supported setup.

## What happens

The tutorial explains each step, prints its ordinary command, and waits for
Enter before executing it. Type `q` or send EOF to stop. It creates a uniquely
named `mb-tutorial-*` directory under the current directory after the first
confirmation. It copies the existing mock simulation examples into that directory.
No simulator, remote source checkout, or additional service is used in the exercise.

All commands execute from that new directory. Existing repository workspaces,
runs, and example files are not changed. An existing tutorial is not resumed or
overwritten by another invocation.

## Basic path: two Jobs, two collections

The default exercise uses test_pass and test_pending from the existing sample.
Only the copied YAML is reduced to these two Jobs; repository examples stay intact.

1. Doctor, prepare and plan explain preparation. The sample has no setup commands,
   so it skips setup. Doctor's OK does not mean
   a test ran; use `doctor --details` for individual diagnostics.
2. Preview the two Jobs, run them serially, and inspect execution records.
3. **Collect 1/2 — results available now:** test_pass becomes PASS; test_pending
   remains PENDING. Exit 2 means an external result is not ready yet.
4. **Make the remaining sample result available:** sample_finish.py --pending-only
   creates the pending Job's done file. This simulates external work finishing;
   it is not an MB repair operation or a real simulation. The marker is specific
   to the sample, not the collector contract.
5. **Collect 2/2 — remaining result:** collect the same run, obtaining only the
   pending Job's result. Both Jobs are now PASS (exit 0); no Jobs are rerun.
6. Inspect the final status, then see saved paths and optional cleanup commands.

No third collect is needed. Repeated collection of final results remains covered
by regression tests rather than another mandatory tutorial step.

## Optional advanced path

```sh
mb tutorial --advanced
```

This starts a separate new exercise with all eight sample Jobs: PASS/FAIL/ERROR/
SKIP, no-check, PENDING and collector faults. It also collects exactly twice.
The first collect exits 2 (unresolved results); the helper completes external
work and removes collector fault markers; the second collect exits 1 because
final FAIL/ERROR verdicts remain. Expected final counts: PASS 5, FAIL 1, ERROR 1,
SKIP 1, no unresolved outcomes. Unlike a collection error, final ERROR is not retried.

Both modes explain expected exit codes before execution and check the resulting
counts. A completed tutorial exits 0. An unexpected failure stops it and keeps
files for inspection.

## Directory and unattended options

```sh
mb tutorial --directory ./my-first-tutorial
mb tutorial --yes
```

`--directory` must name a new directory whose parent already exists. Existing
paths, including symlinks, are refused. `--yes` runs the same sequence without
pausing; explanations and commands are still printed. Neither option enables
cleanup or overwrite.

## Stop, inspect, and continue

Each exercise gets a `GUIDE.md` containing the full manual command sequence,
expected results, directory meanings, and continuation instructions. After `q`,
follow the displayed `cd` command and run the command shown at the paused step.
Do not restart earlier stages unnecessarily: prepare invalidates the saved plan,
and run creates a new run. Collect/status can target a saved run with --run-dir.

Ctrl+C during a child CLI command waits for that command to stop; execution may
need to drain the current Job before returning. Inspect status before continuing
an interrupted run. Jobs never executed cannot be recovered by collect.

The generated directories are:

| Relative path in the exercise | Contents |
| --- | --- |
| `examples/` | Editable copies of the YAML and mock project scripts |
| `work/sample-collector/.reg/` | MB context, plan and state |
| `runs/sample-collector/<run-id>/` | MB execution/collection records, result.json and logs |
| `work/sample-results/<run-id>/<job-id>/` | Project result.txt, sim.log, tarmac.log, mock wave.fsdb, collector call counts |

The sample wave.fsdb is plain text, not a simulator waveform. MB's recorded
execution completion and a collector's judgement remain separate facts.

## Cleanup is your choice

At completion or after stopping, the tutorial prints a shell-quoted `cd` and
`rm -rf -- <exact-tutorial-directory>` command. It does not execute deletion or
ask permission to delete. Keep the directory as a reference or remove it yourself.
Removing it also removes any changes you made inside it.

Continue with [From shell commands to Mockingbird](From_Shell_to_Mockingbird.md)
to connect your own run/collector scripts, or read the
[mock simulation reference](Tutorial_Mock_Simulation.md) for sample details.
