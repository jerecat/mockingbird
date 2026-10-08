# Declarative Execution Contract

The external boundary is a contract. Mockingbird does not understand compile,
sleep, simulation, cleanup, artifact locations, or external scheduler IDs.
Each is an ordinary Job. Normal operation uses max_parallel: 1: Jobs execute
one at a time in list order through the capacity gate. There are no dependencies
or before/after phases. Configuration and runtime reject max_parallel values
other than the integer 1; omission defaults to 1. The scheduler machinery is
retained, but parallel use is disabled by ADR 0009.
A returning submit command does not imply external work has completed.

## Definition fields

The YAML root accepts only `plan`, `meta`, `sources`, `setup`,
`execution`, and `scheduler`. Unknown or reserved root keys are rejected when
loading the definition, before preparation or execution. Similar spellings receive
a suggestion: `setpu` reports `did you mean 'setup'?` instead of silently skipping
setup. Adapter-owned `execution.config` remains an extension namespace.

## Plan: resolve, validate, freeze

```yaml
execution:
  defaults:
    command: ["./run.sh"]
    timeout_s: 600
    collect:
      command: ["./collect.sh"]
      timeout_s: 30
  jobs:
    - test_a
    - test_b
    - id: pause
      command: ["sleep"]
      args: ["3"]
      collect:
        mode: no-check
```

`mb plan` applies defaults, overwrites explicitly specified fields with Job
values, validates every resolved contract, and writes plan.json only on success.
A failed confirmation preserves the last successful plan. Run never reads live YAML.
The required plan name selects `work/<plan>/`; MB chooses all record paths.
Optional `meta` is a JSON-compatible mapping retained as project provenance.
See [Named plans](Named_Plans.md) for identity, complete saved context and migration.
No project command is executed by plan. `doctor` checks command availability;
`dry-run` previews selection from an already validated plan.

Every Job can specify all its fields. Defaults only remove repetitive writing:
500 Jobs still become 500 complete contracts in plan.json.

The resolved payload contains command, args, args_suffix, timeout_s, and collect. Execution
and collection use this payload, never reapply defaults. Core treats it as opaque.

Rules:

- Job fields overwrite defaults by field; arrays and collect mappings are
  replaced as a whole, with no concatenation or recursive merge.
- Explicit args: [] means no arguments. Null is not an omission and is rejected.
- Without args in either place, args becomes [job_id], including for string Jobs.
- A collector command has its own args; absent collector args becomes [job_id].
- Without collect in either place, collect becomes {mode: no-check}.
- command must be a non-empty argv list. args is a string list, possibly empty.
- Execution args_suffix is a string list appended after args; omission means [].
  Job args_suffix replaces the default as a whole; [] removes the default suffix.
  It is frozen in plan.json. Older plans without the field use an empty suffix.
  This field applies to execution, not setup or collector commands.
- Execution and collector-command timeout_s must be finite positive numbers.
- Unknown keys in the declarative execution/default/Job/collect contract, invalid
  types, missing required values, and duplicate/invalid Job IDs fail plan.
- Optional Job metadata is opaque and must be a JSON-serializable mapping.

Common command/args/timeout_s/collect fields at execution level remain supported
as shorthand defaults. Do not define the same default both there and under
execution.defaults. New definitions should use defaults.

## Execution evidence is not a test result

One permitted Job invokes exactly one project command with command + args + args_suffix.
The command runs from the invocation directory included in the confirmed plan.
stdout/stderr are streamed to per-Job log files. The finite local timeout releases
local execution resources; MB does not follow handed-off external work.

The adapter records returncode, timed_out, or launch_error as execution evidence.
These do not automatically become TestResult. Every returned execution is saved
immediately in jobs/<job>/execution.json, the authoritative execution record.
The run's executions.json is a derived snapshot written once when run exits,
including graceful interruption and executor errors. It can be missing or stale
after a write failure; collect reads the per-Job records, not this snapshot.
An executor/plugin exception is recorded too; it may stop further dispatch.
Already saved records survive that error. Unexecuted Jobs remain uncollected.

On Ctrl+C during run, dispatch stops and in-flight executor calls are allowed
to return (or reach their configured timeout) before shutdown completes. The
run is recorded as INTERRUPTED. Collect can then process its saved executions;
Jobs that were never executed stay UNCOLLECTED, so the selected set remains
incomplete. Collect does not resume execution. A second forced interruption or
SIGKILL is not a graceful shutdown and is outside this recovery guarantee.

The generic built-in exit-code collection mode has been removed. If an integration
wants a result based on an exit code, its project-owned collector must explicitly
implement that policy. The demo Python adapters demonstrate project-selected
judgement rules; they are not the generic declarative executor.

## External identity and arguments

Within a run, the contract, execution evidence, and final result are linked 1:1
by Job ID. Across runs the identity is (run_id, job_id).

Both execution and collector commands receive these environment variables:

| Variable | Meaning |
| --- | --- |
| MB_JOB_ID | This Mockingbird Job ID |
| MB_RUN_ID | This invocation's run ID |

The resolved args lists are passed literally: no shell expansion, placeholders,
or hidden extra arguments. Default collector args contains the Job ID, so a
collector normally runs as ./collect.sh test_a. Specify args: [] to use only the
environment, or supply another explicit argument list.

Project commands can use the identity to link their own logs or external work.
MB does not impose an external directory layout or interpret scheduler IDs.
The command collector additionally receives these absolute paths, taken from
the selected Job's saved execution, never from the latest run or current YAML:

| Variable | Meaning |
| --- | --- |
| MB_EXECUTION_JSON | Per-Job execution.json location |
| MB_STDOUT_PATH | Execution command stdout log location |
| MB_STDERR_PATH | Execution command stderr log location |

These variables are supplied when invoking a command collector, not added to
the run/setup command environment by MB. They override same-named inherited
values. Existing IDs, argv and result JSON are unchanged. Collector output goes
to separate collect-* logs; these variables always refer to the original run
command's logs, including repeated collection attempts.

A path does not guarantee that a file exists, is nonempty, or contains a finished
external result. Launch failure, missing files and older aggregate-only runs
can leave evidence unavailable (in particular, old runs may lack execution.json).
Collectors must handle this explicitly; MB does not create replacement evidence
or guess the newest external result. Absolute paths are local to the original
execution environment; moving a run or collecting on another host does not
automatically rebase them.

Supported execution.json fields for command collectors:
- job_id and run_id identify the execution.
- started_at, finished_at and duration_s describe the local command.
- contract.id and contract.payload contain the frozen Job ID and execution
  contract defined above.
- observation may contain returncode, timed_out or launch_error; these fields
  are conditional and are execution evidence, not a verdict.

Other fields, including nested internal ExecutionContext paths, remain adapter
implementation details. Prefer the environment paths to decoding those fields.
See [Collector from execution logs](Collector_From_Logs.md) for a runnable
integration that leaves the producer independent of MB.

## Collection protocol

A collector command must exit zero and print one JSON object:

```json
{"status":"PASS","artifacts":["artifact://project-owned-reference"]}
```

Final statuses: PASS, FAIL, ERROR, SKIP. artifacts defaults to [] and is an opaque
list of strings. Optional reason (string/null) and metadata (mapping) are accepted.
Optional id must match the requested Job ID. Without id, the adapter attaches it.

When the external result is not ready:

```json
{"status":"PENDING","reason":"result not available yet"}
```

PENDING is a collection state, not a TestResult. No final test result is created.
A collector timeout, nonzero exit, invalid output, ID mismatch, or adapter exception
is also unresolved: collection state ERROR. It is retried in the next cycle.
A valid JSON response with status ERROR, on the other hand, is the project's
**final test judgement** and is not retried.

### no-check

The built-in no-check collector returns PASS with artifacts: [] during collect.
It does not inspect execution evidence, even if the command failed to launch or
timed out. This means "no result check requested", not "verified successful".
The plan preserves that choice explicitly; all execution evidence is still saved.

## Repeated collect cycles on one run

```sh
mb run smoke
mb collect smoke --run <chosen-run>
# Later, repeat exactly the same collect command.
```

Each collect call performs one sweep, in selected Job order:

- UNCOLLECTED execution: invoke its collector.
- PENDING or collection ERROR: invoke its collector again.
- COMPLETE: retain the final result without invoking its collector.
- No execution record: leave UNCOLLECTED; do not invent a result.

No executor is rerun. No resident polling loop or background monitor is added.
all performs one execution cycle followed by one collection sweep.

jobs/<job>/collection.json is the authoritative per-Job checkpoint, saved
atomically after each attempt. Final results survive an interrupted collect;
the next collect rebuilds the run-level collection.json and result.json views
from these checkpoints. Those views may be absent or stale until a sweep finishes.
Collector logs use unique names per
attempt. Concurrent collect calls for the same run are rejected using a file lock.
A crash after an external collector runs but before its checkpoint is written can
repeat that call; project collectors should therefore be safe to call again.

result.json contains only final judgements in tests, with separate collection
states. Its summary counts pass/fail/error/skip plus pending, uncollected, and
collection_error; total always refers to the selected set. Until every Job has a
final result, aggregate status is PENDING, even if some final FAILs already exist.
Once complete, aggregate status is FAIL if any final FAIL/ERROR exists, else PASS.
run.json preserves execution status separately from collection_status.

CLI collect/all exit codes: 0 = complete PASS, 1 = complete FAIL, 2 = incomplete
collection. Detailed pending/error state is in result.json and collection.json.

## Capacity and migration

The hard dispatch gate remains min(max_parallel, available_slots()), reserving
locally in-flight executions. Asynchronous capacity providers must account for
already handed-off external work. Existing work is not killed when capacity falls.

Plan, run, collection, and result evidence use schema version 2. New run records
declare checkpoint_storage: per-job. Existing schema-2 runs without that marker
retain their original aggregate execution and collection checkpoints; collection
supports them without migrating or rerunning completed Jobs. Older schemas must
be collected with the version that created them. Replace old collect.mode: exit-code with an explicit
project collector, or choose no-check if result judgement is not required.

Custom Python ExecutionAdapter remains an advanced escape hatch. See
Adapter_Implementation_Guide.md for TestResult versus CollectionAttempt.

## Preparation before the run list

An optional top-level `setup` list uses the same command/args/timeout field rules
without collectors. Its exit codes determine preparation success. This does not
change run/collect judgement rules. See [Setup Contract](Setup_Contract.md).

## Common trailing arguments

Put common leading flags in command and trailing flags in args_suffix:

```yaml
execution:
  defaults:
    command: [./run.sh, --verbose]
    args_suffix: [--mode, regression]
    timeout_s: 3600
  jobs:
    - id: test_a
      args: [--test, test_a]
    - id: test_b
      args: [--test, test_b]
      args_suffix: []  # Omit the common trailing flags for this Job.
```

The first Job invokes `./run.sh --verbose --test test_a --mode regression`.
Argument order is literal; Mockingbird does not interpret flags or apply shell
expansion. Use `examples/args-suffix.yaml` for a runnable demonstration.
After editing execution in an already prepared standard command definition,
repeat plan to adopt the changed contract. Run rejects changes not yet planned;
interactive run offers to update the plan first. Preparation-related changes
still require prepare and setup where applicable. See ADR 0013.
