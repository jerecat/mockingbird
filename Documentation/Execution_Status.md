# Execution and collection status

Three different questions must remain separate:

| Question | Who knows? | Example display |
| --- | --- | --- |
| Is Mockingbird executing a local command? | Mockingbird | Three execution records saved; fourth command executing |
| Is the submitted external simulation running? | User system / collector | Queued or simulation running |
| Have final results been collected? | Mockingbird | Five final outcomes; three unresolved |

## Progress during run

`mb run` and the execution phase of `mb all` print and flush state transitions:

```text
[3/8] test_c: executing
[3/8] test_c: command finished (exit=0)
[4/8] test_d: waiting for capacity
```

Capacity waiting is printed once per Job, not at every poll. The next executing
message appears when capacity permits dispatch. A timeout or launch/executor
error is identified when available in execution evidence. These are execution
facts, not collector judgements.

On normal return, the CLI reports that execution records were saved and directs
you to status for saved collection results. Another terminal may already have
collected some Jobs. In `all`, a collection sweep then follows immediately.
A returning submit command does not mean its external work has finished.

## Inspect from another terminal

```sh
mb status sample-collector
mb status sample-collector --run-dir work/sample-collector/runs/<run-id>
mb status sample-collector --json
mb status sample-collector --details
```

Without `--run-dir`, status selects the workspace's latest run, published before
dispatch starts. It does not select an older run merely because that run has a
collected result. Status works before the first collect and after interrupted
execution or collection.

The default output shows:

- Last recorded execution state, saved execution count and last update time.
- Final collection count, pending count, collection-error count and uncollected
  count. Final ERROR judgements count as final, not collection errors.
- Last recorded collection sweep state and update time.
- An aligned table of each Job's execution state, collection state, and verdict.
- With `--details`, the last collector reason and its observation time.

`status --json` returns this observation snapshot for scripts. The default status
output is now human-readable rather than the old raw `result.json` output.
Consumers requiring final result data should continue reading the run's
`result.json`; see [Record formats](Record_Formats.md) for schema 4. The collector
contract and status snapshot format are unchanged.

## Collect while run is active

From another terminal, run the ordinary commands:

```sh
mb collect sample-collector
mb status sample-collector
```

No new mode is needed. Saved executions are collected; Jobs without execution
records stay UNCOLLECTED. External results that are not ready stay PENDING.
Repeat collect as more records/results become available. Exit code 2 means the
selected set is still incomplete, including when no execution has been saved yet.
Use `--run <run-id>` on each call when you want to stay with a specific run.

Execution can remain RUNNING while some or all results are final. Collect never
updates run.json, stops dispatch, or resumes execution. Records arriving after
inspection can wait until the next sweep. Two collectors on the same run remain
mutually exclusive. This applies to per-Job checkpoint runs, not old aggregate-only
runs. See [Execution contract](Execution_Contract.md#repeated-collect-cycles-on-one-run).

## External state uses the existing collector contract

```json
{"status":"PENDING","reason":"simulation running"}
```

The collector may instead report `queued` or another project-owned explanation.
Status with `--details` displays it as the **last collector report**, with its saved timestamp.
It does not call the collector, query the external queue or start a polling loop.
Run collect again to obtain a newer observation.

## Saved state is not a liveness guarantee

`progress.json` stores the latest local execution transition.
`collection_progress.json` stores the latest collection sweep transition.
Job-level execution and collection checkpoints remain authoritative for saved
execution counts and collection outcomes. Legacy runs use their original
aggregate checkpoints. Stale or missing result views do not hide newer per-Job
collection checkpoints.

RUNNING, EXECUTING and WAITING_CAPACITY describe the last recorded state. A forced
termination can leave those values behind. Status does not check process liveness
and explicitly says so. A timestamp is an observation time, not a heartbeat;
a long-running command can legitimately have an old transition timestamp.

Reads during an active run or sweep can span adjacent transitions. Status is a
read-only observation, not an atomic snapshot across all files. It neither
repairs records nor changes execution or final results.

## Plan history and contents

Use `mb status sample-collector --history` for all runs and recorded results.
Select one with `--run <run-id>`. Add `--plan` to inspect its exact saved plan,
or use `--plan` alone for the current confirmed contents. All views work without
the original YAML. Without a selector, status/collect use the latest-started run;
completion or collection of an older run never changes that default.

See [Record formats](Record_Formats.md): run.json owns execution evidence; result.json owns collection and verdicts.
