# From shell commands to Mockingbird

Start with a command you already understand. This guide uses an existing Git
worktree and adds one piece of Mockingbird configuration at a time. No simulator,
remote repository, or custom Python adapter is required.

## 1. Start with a working script

Assume you invoke MB from a directory called `lab`. Your existing worktree is
`lab/worktrees/experiment`, and its `run.sh` takes a test name:

```sh
cd worktrees/experiment
sh ./run.sh basic
```

For a runnable rehearsal, create `worktrees/experiment/run.sh` with this content.
You can use an ordinary directory instead of a real Git worktree for this exercise.

```sh
#!/bin/sh
set -eu
cd "$(dirname "$0")"
test_name=$1
run_id=${MB_RUN_ID:-manual}
job_id=${MB_JOB_ID:-$test_name}
result_dir="results/$run_id/$job_id"
mkdir -p "$result_dir"
printf 'Running %s\n' "$test_name"
printf 'PASS\n' > "$result_dir/result.txt"
```

The `cd` makes this script use its own worktree even when called from `lab`:

```sh
sh ./worktrees/experiment/run.sh basic
```

These two invocations use the same source directory. Merely specifying a script
path does **not** change the caller's working directory; the script does that.
Run the remaining commands in this guide from `lab`, with `mb` installed.

## 2. Describe one command explicitly

Save this complete definition as `lab/regression.yaml`:

```yaml
plan: worktree-demo
sources: []

execution:
  jobs:
    - id: test_basic
      command: [sh, ./worktrees/experiment/run.sh]
      args: [basic]
      timeout_s: 60
      collect:
        mode: no-check

scheduler:
  capacity_provider: fixed
  max_parallel: 1
  config:
    slots: 1
```

| YAML field | Effect in this example |
| --- | --- |
| `sources: []` | Do not clone anything; the worktree already exists |
| `plan: worktree-demo` | Name the plan; MB keeps its data and runs under `work/worktree-demo/` |
| `id: test_basic` | Identify this Job in execution and collection records |
| `command` + `args` | Execute `sh ./worktrees/experiment/run.sh basic` |
| `timeout_s: 60` | Bound the local command's execution time |
| `collect.mode: no-check` | Return PASS without checking the command or its output |
| fixed capacity, one slot | Allow Jobs to execute one at a time in list order |

`test_basic` is the Job ID; `basic` is the script's argument. They need not match.
The argv lists are literal: no shell expansion or implicit `cd` is performed.

Run each lifecycle step:

```sh
mb prepare regression.yaml
mb plan regression.yaml
mb dry-run worktree-demo
mb run worktree-demo
mb status worktree-demo
mb collect worktree-demo
```

Prepare saves context; plan validates and saves the Job contracts. This example
has no setup list, so setup is not required. For preparation commands and retries,
see [Setup Contract](Setup_Contract.md). Dry-run previews the selection. Run executes the
commands. Collect obtains their results.

**No-check is only useful for Jobs that deliberately need no judgement.** It
returns PASS even if the command failed. To check the file above, add a collector.

## 3. Connect the collector to the same result

Create `worktrees/experiment/collect.py`:

```python
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parent
result = root / "results" / os.environ["MB_RUN_ID"] / os.environ["MB_JOB_ID"] / "result.txt"
if not result.exists():
    outcome = {"status": "PENDING", "reason": "result.txt is not available yet"}
else:
    verdict = result.read_text().strip()
    if verdict not in {"PASS", "FAIL", "ERROR", "SKIP"}:
        outcome = {"status": "ERROR", "reason": "unsupported verdict in result.txt"}
    else:
        outcome = {"status": verdict, "artifacts": [str(result)]}
print(json.dumps(outcome))
```

Replace the Job's `collect` mapping with:

```yaml
      collect:
        command: [python3, ./worktrees/experiment/collect.py]
        args: []
        timeout_s: 10
```

Run **plan again** to adopt the changed execution definition, then run
and collect. No prepare or source acquisition is needed for this change.
Editing YAML does not alter a saved run. A previous no-check result will remain final; use the new run.

Both commands receive `MB_RUN_ID` and `MB_JOB_ID`. The sample producer and
collector agree on `results/<run-id>/<job-id>/result.txt`; that layout belongs
to the scripts, not MB. Collector `args: []` means it uses the environment only.
Its stdout must contain exactly one JSON object; diagnostics belong on stderr.

This example treats an absent result as PENDING. A real collector must decide
whether absence means not finished, failed, or unrecoverable in its own system.
See the [mock simulation tutorial](Tutorial_Mock_Simulation.md) for all outcomes
and recovery from collector failures.

## 4. Share the common fields with defaults

Once one Job works, replace the `execution` section with:

```yaml
execution:
  defaults:
    command: [sh, ./worktrees/experiment/run.sh]
    timeout_s: 60
    collect:
      command: [python3, ./worktrees/experiment/collect.py]
      args: []
      timeout_s: 10
  jobs:
    - id: test_basic
      args: [basic]
    - id: test_read
      args: [read]
    - id: test_write
      args: [write]
```

The resulting commands, in order, are:

```sh
sh ./worktrees/experiment/run.sh basic
sh ./worktrees/experiment/run.sh read
sh ./worktrees/experiment/run.sh write
```

Each Job inherits defaults and replaces explicitly specified fields. Arrays and
`collect` mappings are replaced whole, not merged. If execution `args` is omitted
from both defaults and the Job, it becomes `[job_id]`. Collector arguments follow
the same rule independently. Explicit `args: []` means no middle arguments.

For common trailing flags, set `execution.defaults.args_suffix: [--mode, regression]`.
Execution uses `command + args + args_suffix` in that order. A Job can replace
`args_suffix`, or set it to `[]` to remove the shared suffix. Omission defaults to
`[]`. Try `mb all examples/args-suffix.yaml` and inspect its per-Job stdout logs
for inherited, replaced, and removed trailing arguments.

Repeat prepare/plan after changing this definition. Repeated run creates
new run IDs; collect/status without `--run-dir` select the latest run. To collect
an older run, use the explicit path printed by that run:

```sh
mb collect worktree-demo --run-dir work/worktree-demo/runs/<run-id>
```

## 5. Know which directory owns what

All relative configuration paths in this example assume invocation from `lab`.
The built-in command adapter runs commands and collectors with the **invocation
directory saved at prepare time** as cwd. The definition file's directory and
the script's directory do not implicitly become cwd. The first prepare registers
this project directory against the plan name. Later named commands can run from
any directory and still use this saved cwd and storage. YAML/selection/run-directory
arguments remain ordinary caller-relative paths. For another project, use a
different plan name. See [Named plans](Named_Plans.md) for registration and migration.

| Path under `lab` | Owner and purpose |
| --- | --- |
| `worktrees/experiment/` | User-owned source worktree and scripts |
| `worktrees/experiment/results/<run-id>/<job-id>/` | Results written by these example scripts |
| `work/worktree-demo/.reg/` | MB's saved context, plan, state, and latest-run pointer |
| `work/worktree-demo/exec/` | Custom adapter workspace; not created or used by the standard command adapter |
| `work/worktree-demo/runs/<run-id>/` | MB execution records, collection records, and result.json |
| `work/worktree-demo/runs/<run-id>/jobs/<safe-job-directory>/logs/` | Captured execution/collection stdout and stderr |

MB also allocates per-Job `work/` and `artifacts/` directories for adapters. Their
existence does not mean the command adapter changes into them or copies project
artifacts there. The collector reports artifact paths; MB does not move files.
Deleting only MB's `work/` and `runs/` will not remove this example's project-owned
`worktrees/experiment/results/`.

## 6. Optionally let prepare acquire sources

An existing worktree needs no `sources` entry. To acquire a repository instead,
replace `sources: []` with a real repository URL and revision, for example:

```yaml
sources:
  - name: design
    provider: git
    url: git@github.com:YOUR_ORG/YOUR_REPO.git
    revision: main
```

With the workspace above, the destination is
`lab/work/worktree-demo/sources/design/`. It is **not** the workspace root.
`revision` accepts a branch, tag, or commit; the default is HEAD. Initial prepare
checks out the resolved commit as detached HEAD. Point your command and collector
to scripts in that repository if that is what you intend to execute.

Existing checkouts are reused without pull/reset/checkout, preserving user edits.
Changing YAML's revision does not switch an existing checkout. Users manage
branches and additional worktrees with Git. A separate worktree does not change
MB's configured script paths automatically: update those paths and re-prepare.

Prepare records the observed revision; it does not snapshot source contents or
track subsequent edits. Saved plans freeze command contracts, not script bytes.
See [ADR 0011](ADR/0011-reuse-user-managed-source-trees.md).

For exact field rules, continue to [Execution Contract](Execution_Contract.md).
For capacity and asynchronous submission, use [Integration Guide](Integration_Guide.md).

## Editing and diagnosing your first run

For a prepared standard command setup, edit the execution settings, then confirm:

```sh
mb plan regression.yaml
mb run worktree-demo
mb collect worktree-demo
mb status worktree-demo --history
```

Editing YAML alone does not alter the confirmed plan. Run uses the last successful
confirmation and does not ask whether to update it. A failed confirmation keeps
the prior plan intact. Changing the YAML filename or using another file with the
same plan name is allowed. Each run keeps its own confirmed contents and results.
Use `mb status worktree-demo --run <run-id> --plan` to inspect those contents.

Changes to sources, setup or adapter preparation requirements need prepare, then
optional setup, then plan. Execution and scheduler edits need only plan. Custom
adapter configuration may require setup because its hook can use that config.
Script/source bytes and external tools remain project-managed. See
[Named plans](Named_Plans.md) for reproducibility boundaries and migration.

### Arguments are a list, not a shell command line

To invoke bash ./work/project/run.sh -c -e xxx, write:

    command: [bash, ./work/project/run.sh]
    args: ["-c", "-e", "xxx"]

Each list item is one argument. YAML commas and surrounding quotes are not
passed to the process. A single item "-c -e xxx" stays one argument containing
spaces; it is not split. Numeric arguments must be strings, for example "123".
Use args: [] for no arguments; omitted args inherits defaults or becomes [job_id].
Execution appends args_suffix after args; clear it on sleep Jobs if necessary.

### Working directory

The command runs from the directory recorded by prepare. Neither the YAML file's
directory nor the script's directory implies a change of working directory.
Use a project wrapper that changes directory explicitly if the tool requires it.
A later plan preserves the prepared working directory.

### Find a failure

Run prints an execution error's reason and its record/log paths immediately.
For a nonzero exit or timeout, it also prints where to inspect the record and
stderr. All Job output is saved under:

    work/<plan>/runs/<run_id>/jobs/<safe-job-directory>/logs/stdout.log
    work/<plan>/runs/<run_id>/jobs/<safe-job-directory>/logs/stderr.log
    work/<plan>/runs/<run_id>/jobs/<safe-job-directory>/execution.json

If the command never launched, stdout/stderr may be empty; launch_error in
execution.json records the cause. These are MB's command logs. Project-created
sim.log or waveform paths remain under the script's control.
