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
name: worktree-demo
workspace: ./work/worktree-demo
run_root: ./runs/worktree-demo
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
| `workspace` | Store MB preparation metadata and the plan |
| `run_root` | Put each new run's records under this directory |
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
mb setup regression.yaml
mb plan regression.yaml
mb dry-run regression.yaml
mb run regression.yaml
mb status regression.yaml
mb collect regression.yaml
```

Prepare saves context; setup calls the adapter's setup operation (the built-in
command adapter prepares its directory, not a project build); plan validates
and saves the Job contracts. Dry-run previews the selection. Run executes the
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

Run **prepare, setup, and plan again** to adopt the changed definition, then run
and collect. Editing YAML does not change an already prepared context or saved
run. A previous no-check result will remain final; use the new run.

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
the same rule independently. Explicit `args: []` means no arguments.

Repeat prepare/setup/plan after changing the definition. Repeated run creates
new run IDs; collect/status without `--run-dir` select the latest run. To collect
an older run, use the explicit path printed by that run:

```sh
mb collect regression.yaml --run-dir runs/worktree-demo/<run-id>
```

## 5. Know which directory owns what

All relative configuration paths in this example assume invocation from `lab`.
The built-in command adapter runs commands and collectors with the **invocation
directory saved at prepare time** as cwd. The definition file's directory and
the script's directory do not implicitly become cwd. Keep using the same
invocation directory for this workflow; relative workspace lookup on subsequent
CLI invocations also depends on where you invoke MB.

| Path under `lab` | Owner and purpose |
| --- | --- |
| `worktrees/experiment/` | User-owned source worktree and scripts |
| `worktrees/experiment/results/<run-id>/<job-id>/` | Results written by these example scripts |
| `work/worktree-demo/.reg/` | MB's saved context, plan, state, and latest-run pointer |
| `work/worktree-demo/exec/` | Adapter workspace; not the declarative command's automatic cwd |
| `runs/worktree-demo/<run-id>/` | MB execution records, collection records, and result.json |
| `runs/worktree-demo/<run-id>/jobs/<safe-job-directory>/logs/` | Captured execution/collection stdout and stderr |

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
