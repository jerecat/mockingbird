# Collect during run: design and verification

## Requirement and scope

An operator can run ordinary `mb collect PLAN` in another terminal while `mb run`
is dispatching. Reuse the existing sweep and per-Job checkpoints: no new mode,
background monitor, automatic collection, scheduler callback, or record schema.

The only lifecycle eligibility change is accepting RUNNING for per-Job checkpoint
runs. Keep legacy aggregate-only RUNNING runs rejected. A collector receives only
saved executions; unrecorded Jobs remain UNCOLLECTED. Final results survive run
completion and ordinary repeated collection. Explicit refresh keeps its existing
semantics. Run owns run.json and execution checkpoints; collect owns results.

## Claims, scenarios, and evidence

The verification cases were derived from these invariants before implementation.

| Requirement / invariant | Scenario | Expected evidence | Method / result |
| --- | --- | --- | --- |
| No execution record means no collector call | Hold the first real command, collect by plan from another directory | Exit 2, four UNCOLLECTED, zero collector calls | Independent CLI processes; verified |
| Reuse normal sweep during run | Three saved executions, fourth command held | PASS, PENDING, collection ERROR, UNCOLLECTED; run stays RUNNING | Independent CLI processes; verified |
| Preserve final results; retry unresolved only | Finish external result, collect again, then collect after run ends | Collector counts 1/2/2/1; each executor called once | Call counters and saved evidence; verified |
| Arrival during a sweep can wait for the next sweep | Block collector after execution enumeration, finish run, release collector | First sweep misses last Job; next sweep collects it | Explicit file gates, no guessed timing; verified |
| Collection never owns execution state | Collect before, during and after terminal run publication | run.json and existing execution checkpoint bytes unchanged by collect | Byte comparisons; verified |
| Only published checkpoints are evidence | Invoke collect immediately before atomic execution.json replacement | Temporary file ignored; next collection picks up published record | Bounded os.replace boundary hook; verified |
| One collector per run | Start second collect while first collector is gated | Rejected without extra collector calls | Real CLI process and file lock; verified |
| Refresh uses the same live-run path | Repeat overlapping journey with an initial --refresh | Same recovery/ownership invariants using refresh journal | Parameterized real CLI test; verified |
| Capacity waiting does not block collection | Two submissions occupy queue, third waits | Two PENDING, one UNCOLLECTED; queue/dispatch unchanged | Existing capacity demo test and manual CLI rehearsal; verified |
| Stale RUNNING does not strand saved evidence | Fail terminal run.json write with ENOSPC, restore writes | Saved Jobs collect; stale run.json unchanged | Existing fault injection updated; verified |
| Compatibility boundaries remain explicit | Unknown state or legacy aggregate-only RUNNING | Still rejected; no result generated | Negative tests; verified |

Regression files: `tests/test_collect_during_run.py`,
`tests/test_capacity_gate_demo.py`, and `tests/test_disk_full.py`.
Existing tests cover interruption, malformed collector output, ordinary refresh,
selection, historical runs, source checks, and persistence failures.

## Environment verification

- Python 3.12.3 / PyYAML 6.0.3 / pytest 9.1.1: full suite, 361 passed.
- Python 3.10.19 / PyYAML 5.4.1 / pytest 9.0.3: workaround suite, 359 passed.
  Only the existing `tests/test_cli_aliases.py` exclusion (Python 3.11 tomllib).
- All four existing lifecycle mutation seeds detected in both environments.
- New multi-process tests run in both environments, with and without refresh.

Commands (select the corresponding isolated interpreter):

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /path/to/normal/python -m pytest -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /path/to/compat/python -m pytest -q --ignore=tests/test_cli_aliases.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /path/to/python tools/check_lifecycle_mutations.py
```

## CLI rehearsal and UX review

Ran prepare -> plan -> run, then collect/status while WAITING_CAPACITY, released
one external slot, let run finish, finished remaining external work, and repeated
collect/status. The ordinary commands and the named-plan registry were used.
Relevant actual observations (run paths/timestamps omitted):

```text
Result: PENDING (3 jobs)
  PASS 0  FAIL 0  ERROR 0  SKIP 0
  pending 2  collection error 0  uncollected 1

Execution:  RUNNING (2/3 records)
Collection: 0/3 final; sweep FINISHED

JOB    EXECUTION         COLLECTION   RESULT
sim_a  RECORDED          PENDING      -
sim_b  RECORDED          PENDING      -
sim_c  WAITING_CAPACITY  UNCOLLECTED  -
```

After external completion, the same collect returned exit 0, PASS 3 and no
unresolved Jobs. Run completion no longer claims collection has not started;
status offers collection of saved unresolved executions even during RUNNING.
The partial result explains retrying as records arrive. Rehearsal exposed a
duplicate Next line for mixed PENDING/UNCOLLECTED results; it was removed and
covered by an assertion. Help, README, contract, status guide, and capacity tutorial
were updated. Machine JSON and exit-code contracts are unchanged.

## Limits

This verifies MB's local process/filesystem behavior, not a production farm,
network filesystem, or actual disk exhaustion. No liveness detection, crash
repair, collector cancellation, or automatic polling is added. A saved RUNNING
state may be stale. Missing execution evidence stays uncollected; collectors must
still tolerate retries. A sweep observes published records over time rather than
one atomic snapshot of every file. Result completeness is independent of the
terminal run-state write. Collection waits for its collector commands as usual.
