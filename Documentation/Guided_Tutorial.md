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

The sequence covers:

1. Doctor, prepare, setup and plan, with their purpose and saved paths.
2. A two-Job selection preview without execution.
3. Serial execution of all eight Jobs, then status before collection.
4. PASS/FAIL/ERROR/SKIP, no-check, PENDING and retryable collection errors.
5. Project-owned external completion markers and simulated collector recovery.
6. Collecting only unresolved Jobs, then collecting once more without rerunning
   final collectors.
7. Saved record/artifact locations and optional cleanup instructions.

The sample intentionally produces nonzero **collect** exit codes. The first
collect exits 2 (PENDING); later collects exit 1 (final FAIL/ERROR present).
These are explained before execution. The tutorial checks both expected exit
codes and collection counts; its own successful completion exits 0.
A failed step stops the tutorial and retains files for inspection.

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
Do not restart earlier stages unnecessarily: prepare invalidates setup/plan,
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
