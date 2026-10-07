# Command-line experience

Normal output is intended for people. Saved context and result files remain the
machine contracts; `prepare` no longer dumps the entire context to the terminal.
It reports the prepared set, workspace, source count/materialization, and next
command. Full context is still saved in `<workspace>/.reg/context.json`.

## Start and recover

```sh
mb prepare examples/sample-collector.yaml
mb setup examples/sample-collector.yaml
mb plan examples/sample-collector.yaml
mb dry-run examples/sample-collector.yaml
mb run examples/sample-collector.yaml
mb status examples/sample-collector.yaml
mb collect examples/sample-collector.yaml
```

`mb all <definition>` performs prepare, setup, plan, run, and collect, printing
phase transitions. Use the separate commands when inspecting or editing between
phases. Neither `run` nor `collect` automatically prepares a workspace.

For example, running before preparation reports on stderr:

```text
Error: context not prepared
Required steps:
  mb prepare examples/sample-collector.yaml
  mb setup examples/sample-collector.yaml
  mb plan examples/sample-collector.yaml
Then retry your command.
```

Recovery commands include shell-quoted paths. Missing or stale setup/plan also
produce actionable instructions. Normal errors do not print a Python traceback.
Use `mb --debug <command> <definition>` (or put `--debug` after the command) to
obtain one when investigating a failure. Parser usage errors still show help.

## Human summaries and machine output

| Command | Default | Machine output |
| --- | --- | --- |
| prepare | Prepared workspace, sources, next command | `--json`: full context |
| setup | Completion and next command | Saved workspace metadata |
| plan | Validated Job IDs and next command | Saved `plan.json` |
| dry-run | Selection checklist; no execution | Saved plan remains unchanged |
| run | Per-Job progress, saved run path, collect command | Saved execution records |
| status | Aligned Job table and saved-state counts | `--json`: observation snapshot |
| collect | Verdict counts, unresolved counts, run path, follow-up guidance | `--json`: full collection result |
| all | Phase progress and collection summary | Saved files in the printed run path |
| doctor | Aligned connection checks | No JSON mode |

`prepare --json`, `collect --json`, and `status --json` write one JSON document to
stdout. Redirect stdout to a file to consume it. Diagnostics go to stderr.
`collect --json` returns the full result, not just its `summary` member.
Scripts that previously parsed the default prepare/collect/all output should
use explicit JSON options or saved files. Persisted schemas are unchanged.

```sh
mb prepare examples/sample-collector.yaml --json > context-copy.json
mb collect examples/sample-collector.yaml --json > collected-result.json
mb status examples/sample-collector.yaml --details
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
