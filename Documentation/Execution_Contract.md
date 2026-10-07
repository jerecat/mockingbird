# Declarative Execution Contract

The external boundary is a contract. Mockingbird does not understand compile,
sleep, simulation, cleanup, artifact locations, or external scheduler IDs.
Each is an ordinary Job. Normal operation uses max_parallel: 1: Jobs execute
one at a time in list order through the capacity gate. There are no dependencies
or before/after phases. Configuration and runtime reject max_parallel values
other than the integer 1; omission defaults to 1. The scheduler machinery is
retained, but parallel use is disabled by ADR 0009.
A returning submit command does not imply external work has completed.

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
A failed plan validation removes the old plan so it cannot accidentally run.
No project command is executed by plan. `doctor` checks command availability;
`dry-run` previews selection from an already validated plan.

Every Job can specify all its fields. Defaults only remove repetitive writing:
500 Jobs still become 500 complete contracts in plan.json.

The resolved payload contains command, args, timeout_s, and collect. Execution
and collection use this payload, never reapply defaults. Core treats it as opaque.

Rules:

- Job fields overwrite defaults by field; arrays and collect mappings are
  replaced as a whole, with no concatenation or recursive merge.
- Explicit args: [] means no arguments. Null is not an omission and is rejected.
- Without args in either place, args becomes [job_id], including for string Jobs.
- A collector command has its own args; absent collector args becomes [job_id].
- Without collect in either place, collect becomes {mode: no-check}.
- command must be a non-empty argv list. args is a string list, possibly empty.
- Execution and collector-command timeout_s must be finite positive numbers.
- Unknown keys in the declarative execution/default/Job/collect contract, invalid
  types, missing required values, and duplicate/invalid Job IDs fail plan.
- Optional Job metadata is opaque and must be a JSON-serializable mapping.

Common command/args/timeout_s/collect fields at execution level remain supported
as shorthand defaults. Do not define the same default both there and under
execution.defaults. New definitions should use defaults.

## Execution evidence is not a test result

One permitted Job invokes exactly one project command with command + args.
The command runs from the invocation directory saved in context.json.
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
Internal ExecutionContext paths remain an adapter implementation interface.

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
mb run regression.yaml
mb collect regression.yaml --run-dir runs/<chosen-run>
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
