# Demos

## Mock simv: run, collect, artifacts and recovery

Step-by-step Japanese walkthrough: [模擬シミュレーション接続チュートリアル](Tutorial_Mock_Simulation.md).

No simulator, licence, farm or source clone is required. These scripts create
small text files as a stand-in for a user's simulation system. `wave.fsdb` is
explicitly a text placeholder, NOT a valid waveform file for a waveform viewer.

| Job | First collect | After external completion/recovery |
| --- | --- | --- |
| test_pass | PASS | retained |
| test_fail | FAIL | retained |
| test_error | final ERROR | retained, not retried |
| test_skip | SKIP | retained |
| test_pending | PENDING | PASS |
| test_collect_error | collection error (exit 7) | PASS |
| test_bad_json | collection error (invalid JSON) | PASS |
| test_no_check | PASS without calling collector | retained |

Run from the repository root with the installed virtual environment active:

```bash
mb prepare examples/sample-collector.yaml
mb setup examples/sample-collector.yaml
mb plan examples/sample-collector.yaml
mb run examples/sample-collector.yaml
mb collect examples/sample-collector.yaml
mb status examples/sample-collector.yaml
```

First collect: total=8, pass=2, fail=1, error=1, skip=1, pending=1,
uncollected=0, collection_error=2. Aggregate status is PENDING and collect exits 2.
Run all commands individually; the nonzero collect exit is intentional.
All mock execution commands return zero, including the Job with a FAIL verdict.

- `examples/sample_run.py` writes `result.txt`, `tarmac.log`, `wave.fsdb`,
  `sim.log` and (except for the pending case) a `done` marker. No JSON is written.
- `examples/sample_collect.py` reads those files, decides the result and prints
  one JSON object to stdout, including absolute artifact paths.
- Mockingbird invokes the collector and stores its response in the run's result.
  It does not copy or interpret the artifact files.

The project-owned files live at `work/sample-results/<MB_RUN_ID>/<MB_JOB_ID>/`.
The collector reads the plain-text verdict in `result.txt`. No completion marker
means PENDING, even when files exist. A completed run with a missing or invalid
verdict means final ERROR. A collector failure is a retryable collection error.

Use the directory basename printed by `mb run` as the run ID below:

```bash
RUN_ID=20261007_140000_000000_sample-collector  # replace with your actual run ID
ls "work/sample-results/$RUN_ID/test_pass"
cat "work/sample-results/$RUN_ID/test_fail/result.txt"

# Simulate the external system completing and its result service recovering.
# This touches only project-owned sample files, never Mockingbird's records.
python3 examples/sample_finish.py "$RUN_ID"
mb collect examples/sample-collector.yaml --run-dir "runs/sample-collector/$RUN_ID"
mb status examples/sample-collector.yaml --run-dir "runs/sample-collector/$RUN_ID"
```

Second collect: total=8, pass=5, fail=1, error=1, skip=1; all unresolved counts
are zero. Collection is complete, aggregate status is FAIL, and collect exits 1.
Only the three previously unresolved Jobs were retried. Each executed collector
appends a line to its `collector_calls.txt`: final Jobs have one call, recovered
Jobs have two, and no-check has no such file. A third collect makes no calls.
Repeating collect does not rejudge final results after log edits. Start a new run
to try another final verdict; each run uses its own project output directory.

To inspect the collector's output directly, substitute the run ID printed by run:

```bash
MB_RUN_ID="$RUN_ID" MB_JOB_ID=test_pass python3 examples/sample_collect.py
```

Replace the sample directory convention, completion check and verdict parsing
with your project's rules. Direct invocation also increments the demo call count.
The JSON is created by this user-owned collector;
the run-level `result.json` is created by Mockingbird.

## Direct Linux commands (serial)

```bash
mockingbird doctor examples/linux-commands.yaml
mockingbird all examples/linux-commands.yaml
```

Runs `pwd`, `ls -la`, `sleep 1`, `mkdir`, and `rmdir` directly in list order,
with `max_parallel: 1`. No project wrapper is needed. The next command starts
after the previous command returns and capacity permits it.

Defaults supply the timeout and empty arguments; each Job supplies its command
and any argument overrides. Plan resolves the omitted collector to `no-check`.
All commands run from the invocation directory. The temporary demo directory is
`work/linux-commands/demo-directory`; the final Job removes it when empty.

Expected: five execution records and five no-check PASS results. A no-check PASS
does not verify command success: inspect `executions.json` for return codes and
timeouts, and per-Job logs for output. The run files are under
`runs/linux-commands/<run-id>/`.

## Linux sanity

```bash
mockingbird doctor examples/sanity-linux.yaml
mockingbird all examples/sanity-linux.yaml
```

Purpose: prove the no-project-Python declarative command path, connection probes,
lifecycle, capacity gating, per-job execution contexts, streamed logs, and
canonical result flow on an ordinary Linux machine.

## Explicit FAIL rerun

```bash
mockingbird all examples/regression-fail-demo.yaml || true
mockingbird run examples/regression-fail-demo.yaml --failed-from runs/<chosen-run>
mockingbird collect examples/regression-fail-demo.yaml
```

Purpose: demonstrate explicit FAIL provenance and Job-granularity rerun.

## Self-hosted demo

```bash
mockingbird doctor examples/self-host.yaml
mockingbird all examples/self-host.yaml
```

Purpose: mockingbird schedules groups of its own pytest tests through the concrete
`selftest` adapter. Core still sees only Jobs and canonical execution/result
evidence.

## External adapter demo (advanced escape hatch)

```bash
pip install -e examples/external_adapter
mockingbird doctor examples/external-adapter.yaml
mockingbird all examples/external-adapter.yaml
```

Purpose: prove project integration, probe, process utility, and canonical result
collection without editing the `mockingbird` package.


## Virtual operations rehearsal

Run the actual CLI against an isolated simulated external service:

```sh
python -m pytest -q -s tests/test_virtual_operations.py
```

This covers pending/error recovery, immutable completed results, capacity gating,
and a failed-only rerun. See `Virtual_Operations.md` for the observed cycle table.
