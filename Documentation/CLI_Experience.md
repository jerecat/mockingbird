# Command-line experience

Normal output is intended for people. Saved context and result files remain the
machine contracts; `prepare` no longer dumps the entire context to the terminal.
It reports the prepared plan, storage path, source count/materialization, and next
command. Full context is still saved in `<workspace>/.reg/context.json`.

For the interactive first-run walkthrough, use `mb tutorial` after installing
from a clone. It uses a new directory and prints optional manual cleanup commands.
See [Guided tutorial](Guided_Tutorial.md). The basic path ends with two PASS
results after two collections. `--advanced` adds intentional failure verdicts and
collector faults; a completed tutorial still exits zero.

## Start and recover

```sh
mb prepare examples/sample-collector.yaml
mb plan sample-collector
mb dry-run sample-collector
mb run sample-collector
mb status sample-collector
mb collect sample-collector
```

`mb all <definition>` performs prepare, setup, plan, run, and collect, printing
phase transitions. Use the separate commands when inspecting or editing between
phases. Neither `run` nor `collect` automatically prepares a workspace.

For example, running before preparation reports on stderr:

```text
Error: plan 'sample-collector' is not registered.
  For a new plan, run mb prepare <definition.yaml> from its project directory.
  To restore a registration, run mb prepare <definition.yaml> from its original project directory.
```

Before the first prepare, supply your YAML path in place of `<definition.yaml>`.
Once registered, named commands resolve the same plan from every directory.
Unknown names and missing registered locations are errors; an existing plan with
no runs can still report `No runs yet.` in history. See [Named plans](Named_Plans.md).
After prepare, recovery commands use the recorded, shell-quoted YAML path. Missing or stale setup/plan also
produce actionable instructions. Normal errors do not print a Python traceback.
Use `mb --debug <command> <definition>` (or put `--debug` after the command) to
obtain one when investigating a failure. Parser usage errors still show help.

## Human summaries and machine output

| Command | Default | Machine output |
| --- | --- | --- |
| prepare | Prepared workspace, sources, next command | `--json`: full context |
| setup | Per-command progress, attempt path, next command; skipped when not required | Per-attempt records and logs |
| plan | Validated Job IDs and next command | Saved `plan.json` |
| dry-run | Selection checklist; no execution | Saved plan remains unchanged |
| run | Per-Job progress, saved run path, collect command | Saved execution records |
| status | Aligned Job table and saved-state counts | `--json`: observation snapshot |
| collect | Verdict counts, unresolved counts, run path, follow-up guidance | `--json`: full collection result |
| all | Phase progress and collection summary | Saved files in the printed run path |
| doctor | Grouped pre-run summary; failures/warnings remain visible | `--details`: all diagnostic checks; no JSON mode |

`prepare --json`, `collect --json`, and `status --json` write one JSON document to
stdout. Redirect stdout to a file to consume it. Diagnostics go to stderr.
`collect --json` returns the full result, not just its `summary` member.
Scripts that previously parsed the default prepare/collect/all output should
use explicit JSON options or saved files. Schema-3 plan.json embeds the original
input, resolved Jobs and complete execution context. Each run saves that plan.
No original YAML is needed to inspect or collect the run. Use `status --history`
to list runs and `status --run <run-id> --plan` to inspect historical contents.
JSON record schemas and collector outputs are unchanged by name registration.

```sh
mb prepare examples/sample-collector.yaml --json > context-copy.json
mb collect sample-collector --json > collected-result.json
mb status sample-collector --details
```

Status separates JOB, EXECUTION, COLLECTION, and RESULT into aligned columns.
`--details` adds multiline collector reasons and observation timestamps. Times
are displayed in the local timezone with a UTC offset and second precision;
JSON preserves saved timestamps. Very long Job IDs can exceed terminal width.

Status reads saved observations; it does not check liveness or invoke collectors.
See [Execution and collection status](Execution_Status.md).

## Exit codes and interruption

- `0`: command succeeded; for collect/all, aggregate PASS.
- `1`: operation failed, doctor checks failed, or collect/all reached a non-PASS
  final result.
- `2`: collect/all remains PENDING, or argparse rejected command-line syntax.
- `130`: interrupted by Ctrl+C.

PENDING and collection errors can be revisited with collect on the same run.
Final results are not recollected. Jobs without execution records cannot be
collected; `run` creates a new run. Execution interruption retains completed
records after draining the active worker; this can take until command completion
or timeout. Forced termination is not equivalent to graceful interruption.

For future CLI changes, apply the repository skill at
`.skills/review-cli-ux/SKILL.md`. It is a repository reference, not an automatically
installed personal skill.

## Reading doctor output

`doctor` summarises definition validation, execution/collection checks, source
checks (when configured), and execution capacity. `OK` means the configured
checks passed, not that a simulation ran or a result passed. It does not prepare
the workspace or execute Jobs. The command adapter checks executable lookup;
for `python3 script.py`, finding Python does not establish that the script exists
or behaves correctly. Plan validation and actual execution remain separate steps.

Use `mb doctor <definition> --details` for every individual check and executable
path. The diagnostic `plugin` entries mean that MB loaded an implementation;
they are not separately installed services. Default output keeps failures and
warnings with their identifying check and reason. A warning gives ATTENTION,
not an all-clear summary; the existing exit policy remains unchanged (FAIL = 1,
otherwise 0). Fixed capacity zero is valid but stops dispatch, so it is shown as
waiting rather than an execution-ready slot.

Setup command lists and edit/retry behaviour are described in [Setup Contract](Setup_Contract.md).
With no setup list, the standard command adapter permits prepare directly followed by plan.

## Edit execution and replan

Confirm execution/scheduler edits with `mb plan PLAN`. Setup/run/dry-run/status/
collect take the plan name. Run does not reread YAML or offer to update it.
Failed confirmation leaves the previous plan intact. Sources/setup changes still
require explicit preparation; see [Named plans](Named_Plans.md).

Launch errors print the reason and execution.json/stderr.log paths immediately.
Nonzero exit codes and timeouts also print these paths. This reports execution
evidence and does not change collector or no-check verdict semantics.

## Visual grouping

Human output uses one blank line at a change of meaning: a phase transition,
Job start or capacity-wait transition, summary, or follow-up action. A Job's
completion and error evidence stay together. Supporting paths and multiline
error details are indented under their owning message. Table rows and Job lists
stay compact; separate the table/list from surrounding guidance instead of
spacing every row. Status groups execution and collection observations separately.

For example (paths shortened here only):

```text
Checking sources...
Sources: 0 checked, 0 tracked-dirty, 0 unknown

[1/2] compile: executing
[1/2] compile: command finished (exit=0)

[2/2] smoke: executing
[2/2] smoke: command finished (exit=0)

Execution finished: 2 execution records
  External completion not checked.
  Collection: use status to inspect saved results
  run: .../runs/<run-id>

Next: mb collect smoke --run-dir .../runs/<run-id>
```

The same grouping applies to stderr recovery guidance and tutorial commands,
outputs, and expected exit codes. Formatting is owned by the CLI: subprocess
stdout/stderr, saved logs, record schemas, JSON modes, and exit codes are not
reformatted. A child's own output can still be dense or lack a trailing newline.
Human formatting is not a machine parsing contract. No terminal-width detection,
new dependency, stream wrapper, or screen-clearing behavior is required.

Review a complete terminal transcript, including `all` and tutorial composition,
not just isolated helper output: check that the current Job, its evidence, the
summary, and the next action can be located without reading every line. Also
inspect redirected output, stderr recovery, and JSON parsing. More blank lines
are not inherently better; preserve compact comparison rows and keep related
information adjacent.

## Collection summary

Human `collect` output separates collection progress from the overall verdict:

```text
Collection: 1/3 complete
  PASS 1  FAIL 0  ERROR 0  SKIP 0
  pending 2  collection error 0  uncollected 0
```

The denominator is the number of Jobs selected for this run. Complete means a
Job has a final PASS, FAIL, ERROR, or SKIP verdict; it does not mean it passed.
Pending, collection errors, and uncollected Jobs do not count as complete.
`Result: PASS` or `Result: FAIL` appears only when all selected Jobs have final
verdicts. `status` uses the same `complete` wording for its collection count.
JSON records retain the existing PENDING status and exit codes are unchanged.

In the human `status` table, execution `COMPLETE` means an execution record was
saved after the command attempt. It does not imply command success or external
simulation completion. JSON continues to use `RECORDED`; other execution states
are displayed unchanged. Collection `COMPLETE` means a final verdict is available.
