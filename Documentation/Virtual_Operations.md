# Virtual operations rehearsal

Implementation under test: `02c91edf4014b7ef0a6045385a9e0934c8fcd6e7`.

This rehearsal exercises the actual CLI in separate processes. Project-owned
commands simulate an external submission/result service using files in an isolated
workspace. It does not require VCS, an external farm, or a resident background
process. Completion and repair are controlled explicitly, so the scenario is
reproducible without long sleeps or timing-dependent external jobs.

## Reproduce

```sh
python -m pytest -q -s tests/test_virtual_operations.py
```

The test writes `operations-report.json` and `cli-transcript.json` in its pytest
temporary directory, alongside the generated definition, external evidence and
Mockingbird run files. The transcript includes every CLI invocation and exit code.

## Selected set

| Job | Execution | Collector |
| --- | --- | --- |
| compile | Ordinary command, returns zero | no-check |
| pause | Short local wait, explicit empty args | no-check |
| sim_pass | Submit and return; PASS already available | Project collector |
| sim_late | Submit and return; result published later | Project collector |
| sim_fail | Submit returns zero; external result FAIL | Project collector |
| sim_retry | Submit and return; result service fails once | Project collector |
| cleanup | Returns 9 intentionally | no-check |

The defaults provide the common command, finite timeout and collector. Per-Job
contracts override command/args/collector where required. The selected list is
fixed within the run. max_parallel is 1 to make local command order observable;
this does not add dependencies or wait for external completion.

## Observed result

| Cycle | PASS | FAIL | PENDING | Collection error | Aggregate | CLI exit |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| First collect | 4 | 1 | 1 | 1 | PENDING | 2 |
| Collect again: result service recovers | 5 | 1 | 1 | 0 | PENDING | 2 |
| Publish delayed result and collect | 6 | 1 | 0 | 0 | FAIL, complete | 1 |
| Collect an already complete run | 6 | 1 | 0 | 0 | FAIL, complete | 1 |
| Repair and rerun only sim_fail in a new run | 1 | 0 | 0 | 0 | PASS, complete | 0 |

A complete run is not necessarily a passing run. All seven results are final
at the third cycle, so collection is complete despite one final FAIL.

## Assertions exercised

- doctor/prepare/setup/plan/dry-run/run/collect/status all use the real CLI.
- Plan contains a complete command/args/timeout/collector contract for every Job.
- Dry-run does not submit work.
- Capacity reports zero twice; no command starts until the gate opens.
- Serial execution follows the selected list order.
- Every execution is recorded, including cleanup's returncode 9.
- no-check returns PASS for cleanup without turning the return code into a test
  judgement. Conversely, sim_fail returns zero from submission but collects FAIL.
- The second sweep calls only sim_late and sim_retry; the third calls only sim_late.
- Execution evidence remains byte-for-byte unchanged during every collect.
- Completed results remain unchanged; a fourth collect invokes no project command
  and leaves the collection checkpoint unchanged.
- `--failed-from` selects only sim_fail, records the source run/result hash, and
  creates a different run identity. The old result remains unchanged.
- A misspelled Job field (`timeuot_s`) fails plan; run is then rejected without
  submitting any work.

The rehearsal passed. No product-code correction was required by this scenario.
Real farm accounting, simulator integration and filesystem failure behavior are
outside this simulated service test. Existing tests separately cover interrupted
collection, concurrent-collect exclusion and incremental execution evidence.
