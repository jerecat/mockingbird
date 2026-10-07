# Mock Simulation Integration Tutorial

No simv, simulator licence or external queue is required. This tutorial creates
small text files to demonstrate how to connect a user-owned execution command
and collector to Mockingbird. No additional source repositories are cloned.

## 1. Prepare your environment

Run these commands from the Mockingbird repository root. If Mockingbird is already
installed in your virtual environment, just activate it.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

| File | Responsibility |
| --- | --- |
| `examples/sample-collector.yaml` | Connect Jobs to execution and collection commands |
| `examples/sample_run.py` | Stand in for simv and create project-owned files |
| `examples/sample_collect.py` | Interpret files and print judgement JSON with artifact references |
| `examples/sample_finish.py` | Simulate external completion and collection service recovery |

Both execution and collection identify their target through the `MB_RUN_ID` and
`MB_JOB_ID` environment variables. This example uses these variables rather than
command-line arguments, so `args` is empty in the YAML definition.

## 2. Plan and execute

```sh
mb doctor examples/sample-collector.yaml
mb prepare examples/sample-collector.yaml
mb setup examples/sample-collector.yaml
mb plan examples/sample-collector.yaml
mb run examples/sample-collector.yaml
```

Eight Jobs execute in list order. Copy the final directory name from the printed
`run:` path. Replace the example ID below with the ID from your own run.

```sh
RUN_ID=20261007_140000_000000_sample-collector
RUN_DIR="runs/sample-collector/$RUN_ID"
```

## 3. Inspect the project-owned files

```sh
ls "work/sample-results/$RUN_ID/test_pass"
cat "work/sample-results/$RUN_ID/test_pass/result.txt"
cat "work/sample-results/$RUN_ID/test_fail/result.txt"
cat "work/sample-results/$RUN_ID/test_pass/sim.log"
```

Each Job creates `result.txt`, `tarmac.log`, `wave.fsdb` and `sim.log`.
All four are mock text files. `wave.fsdb` is not a valid FSDB file and cannot be
opened as a waveform in a waveform viewer. Completed Jobs also have a `done`
marker; `test_pending` does not have one yet.

The user-owned execution script has not created any JSON. `result.txt` contains
only a plain-text PASS, FAIL, ERROR or SKIP verdict. Every execution command
returns exit code 0, independently of that verdict.

## 4. Collect results for the first time

```sh
mb collect examples/sample-collector.yaml --run-dir "$RUN_DIR"
echo $?
mb status examples/sample-collector.yaml --run-dir "$RUN_DIR"
```

| Job | First outcome | Meaning |
| --- | --- | --- |
| test_pass | PASS | Successful test judgement |
| test_fail | FAIL | Mock scoreboard mismatch |
| test_error | ERROR | Mock simulator fatal error; a final judgement |
| test_skip | SKIP | Unsupported configuration |
| test_pending | PENDING | Waiting for completion |
| test_collect_error | collection_error | Collector exits with code 7 |
| test_bad_json | collection_error | Collector returns invalid JSON |
| test_no_check | PASS | Judgement omitted; no collector is called |

Expected counts: `total=8, pass=2, fail=1, error=1, skip=1, pending=1,
uncollected=0, collection_error=2`.

Because some outcomes are unresolved, the aggregate status is PENDING and collect
returns exit code **2**. This is intentional. Run the commands individually and
continue with the next step.

`sample_collect.py` creates the JSON. Mockingbird receives it and saves per-Job
collection records and the run-level `result.json`. The `artifacts` list contains
absolute paths to the four files above; it is empty for no-check. Mockingbird
does not copy the artifact files themselves.

## 5. Complete external work, recover the service and collect the same set again

```sh
python3 examples/sample_finish.py "$RUN_ID"
mb collect examples/sample-collector.yaml --run-dir "$RUN_DIR"
echo $?
mb status examples/sample-collector.yaml --run-dir "$RUN_DIR"
```

The finish helper changes only project-owned completion and fault markers.
It neither changes Mockingbird's records nor repeats execution.

The PENDING Job and both collection-error Jobs now return PASS. Expected counts
are `total=8, pass=5, fail=1, error=1, skip=1`, with all unresolved counts at zero.
Collection is complete, but the retained final FAIL and ERROR judgements make
the aggregate status FAIL and the exit code **1**. Unlike a collection error,
a final ERROR judgement is not retried.

## 6. Verify that final outcomes are not collected again

```sh
wc -l "work/sample-results/$RUN_ID"/*/collector_calls.txt
mb collect examples/sample-collector.yaml --run-dir "$RUN_DIR"
wc -l "work/sample-results/$RUN_ID"/*/collector_calls.txt
```

The four Jobs with initially final collector outcomes have one line each. The
three recovered Jobs have two lines each. The no-check Job has no call record.
The third collect does not change these counts. This file is tutorial-only
instrumentation for observing collector calls.

## 7. Connect your real system

- Replace file creation in `sample_run.py` with actual simv execution or submission
  to your external queue.
- Adapt the completion check and verdict parsing in `sample_collect.py` to your
  project's result format.
- Return references to logs, waveforms and other evidence in `artifacts`.
- Remove the tutorial-only finish helper, fault markers and call-count recording.

File locations, completion markers and judgement rules are project-owned
conventions. The return format Mockingbird requires is the collector's JSON.

Use `mb run` to create a new run when trying a different final verdict. Editing
the original logs does not cause repeated collect to rejudge final results.
Each run's files remain in its own directory.
