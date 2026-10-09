# Where to read run records and results

All paths below are relative to `work/<plan>/runs/<run-id>/`.

| Question | File |
| --- | --- |
| Which confirmed commands and configuration were used? | `plan.json` |
| What was selected, when did dispatch run, and what source state was observed? | `run.json` |
| Which results are available, which are unresolved, and what passed or failed? | `result.json` |

`run` creates and finishes run.json. `collect` never writes run.json: it publishes
result.json after a collection sweep. Before the first successful sweep, result.json
may not exist. `mb status PLAN` shows recorded progress, including partial checkpoints
left by an interrupted sweep. `mb status PLAN --history` lists runs.

## run.json: execution record (schema 3)

| Field | Meaning |
| --- | --- |
| schema_version | Format version, 3 |
| plan, run_id | Plan and execution identity |
| status | RUNNING, EXECUTED, INTERRUPTED or ERROR |
| started_at, finished_at, duration_s | MB dispatch/execution timing, not external simulation completion |
| error | Execution-control error, when present |
| selection | Selected Job IDs and selection provenance |
| source_observations | Prepare-time commit, run-start HEAD and `tracked_dirty` (true/false/null) per supported source |
| scheduler | Recorded dispatch settings |
| jobs | Job record/log locations |
| checkpoint_storage | Internal checkpoint layout |

EXECUTED means execution commands returned, not that the DUT passed. A forced
process termination may leave RUNNING in the record. Collection adds no fields
and does not change execution status, source observations or timestamps.

## result.json: collection and verdicts (schema 4)

| Field | Meaning |
| --- | --- |
| schema_version | Format version, 4 |
| plan, run_id | Identity retained so the result can be consumed independently |
| started_at | Copied run start time for ordering results across runs |
| generated_at | Time this aggregate was generated, including repeated collection |
| status | PASS or FAIL once complete; PENDING while any Job is unresolved |
| collection_complete | Whether all selected Jobs have final verdicts |
| summary | Final verdict and unresolved collection counts |
| jobs | One entry per selected Job: collection state and its optional final result |

There is no top-level execution finished_at or duration_s; read run.json for those.
Job result duration_s, if present, remains the collector/adapter-reported duration.

Example of a partially collected result (illustrative identifiers and times):

```json
{
  "schema_version": 4,
  "plan": "smoke",
  "run_id": "run-001",
  "started_at": "2026-10-09T00:00:00+00:00",
  "generated_at": "2026-10-09T00:05:00+00:00",
  "status": "PENDING",
  "collection_complete": false,
  "summary": {
    "total": 2, "pass": 0, "fail": 1, "error": 0, "skip": 0,
    "pending": 1, "uncollected": 0, "collection_error": 0
  },
  "jobs": {
    "test_a": {
      "state": "COMPLETE",
      "attempts": 1,
      "updated_at": "2026-10-09T00:04:59+00:00",
      "result": {
        "id": "test_a", "status": "FAIL", "duration_s": 120.0,
        "reason": "Data mismatch", "metadata": {}, "artifacts": ["/path/to/sim.log"]
      }
    },
    "test_b": {
      "state": "PENDING", "attempts": 1,
      "updated_at": "2026-10-09T00:05:00+00:00",
      "reason": "Simulation has not finished"
    }
  }
}
```

`jobs.<id>.state` is the collection state: UNCOLLECTED, PENDING, ERROR or COMPLETE.
`jobs.<id>.result.status` is the final verdict: PASS, FAIL, ERROR or SKIP.
A collection ERROR can be retried; a final ERROR is a fixed verdict. Result data
appears only once, within its Job entry. Unresolved entries may carry a reason,
artifacts and adapter-provided ID; UNCOLLECTED entries may have no updated_at yet.
Summary error counts final ERROR verdicts; collection_error counts retryable errors.

Repeated collect retains final Job entries and retries unresolved executed Jobs.
The aggregate is replaced atomically; a failure before publication can leave an
older result.json. Per-Job collection.json files are recovery checkpoints, not an
alternative user report. Run-level collection.json is an internal derived view
for current runs (legacy runs may use it as their checkpoint).

## Compatibility

Only result.json moves to schema 4. Run and plan remain schema 3. New results
replace schema-3 `tests` plus `collection` with `jobs`; external consumers must
update their field access. `collect --json` returns this new result format.
Collector output contracts and `status --json` are unchanged.

FAIL selection accepts both old `tests` arrays and new `jobs` entries. Existing
runs remain readable and collectable. Recollecting an old run publishes a schema-4
result, but leaves its run.json byte-for-byte unchanged, including any historical
collection_status/result_status/collected_at fields. Those legacy fields are not
updated and must not be used to read current results; use result.json.

Source checks print `Checking sources...` before observation and a compact count
afterwards. Only supported observations count as checked; unsupported providers
are omitted. Errors remain visible and are recorded with an unknown dirty state.
Git checks exclude untracked files (including in submodules). `tracked_dirty: false`
does not establish a reproducible worktree. Old `dirty` records remain readable.
TTY progress grows dots on one line; redirected output contains no animation.
The CLI constants `SOURCE_PROGRESS_INTERVAL_S` (0.4 seconds) and
`SOURCE_PROGRESS_MAX_DOTS` (6) control the animation. Each Git observation command
retains its existing 10-second subprocess timeout; filesystem stalls can still
make checks slow.

Use `mb run PLAN --skip-source-check` to bypass all run-start source observations
(including Git HEAD and tracked-dirty checks). Execution and collection work as
usual. The CLI prints `Sources: skipped (--skip-source-check)`; run.json records
`source_check_skipped: true` and empty `source_observations`. Otherwise the flag
is false. Missing flags in older records do not establish whether checks ran.
`save` warns that run-time source state is unknown and uses the preparation
revision when available. `mb all YAML --skip-source-check` supports the same
option, but still performs normal preparation and its source acquisition.

## Exceptional collector refresh

For `collect --refresh`, result.json additionally records `collection_config`
with `refreshed_at` and a Job-ID-to-collector-settings map named `collectors`.
Run-level collection.json becomes authoritative for refreshed runs and contains
that mapping plus current Job checkpoints. Existing per-Job collection checkpoints
are ignored for these runs. See [Collector repair](Collector_Refresh.md) for
acceptance, interruption and recovery semantics.
