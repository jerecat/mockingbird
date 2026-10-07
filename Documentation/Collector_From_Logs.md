# Locate project results from execution logs

An existing tool often prints its output directory or external queue ID.
The collector can read that message directly from MB's saved execution log.
The producer does not need to use MB_RUN_ID, write a submission mapping file,
or change its own result-directory layout.

Run from the clone root:

    mb all examples/collector-from-log.yaml

Expected: two PASS results. Each run command creates a uniquely named directory
under work/log-location-results and prints an absolute path:

    RESULT_DIR=/.../work/log-location-results/simulation-...

The collector reads MB_STDOUT_PATH, extracts the one RESULT_DIR, and reads
result.txt there. It does not search for the newest directory or build an MB
job directory from the Job ID. Existing tools may use different log syntax;
that parser belongs to your collector, not MB.

Files:
- examples/log_location_run.py: mock producer, with no MB environment dependency.
- examples/log_location_collect.py: reference collector.
- examples/collector-from-log.yaml: runnable definition.

## Inputs and failures

MB_STDOUT_PATH and MB_STDERR_PATH point to the run command's logs.
MB_EXECUTION_JSON points to its per-Job execution record, if available.
All are absolute paths for the selected run and Job, including explicit
--run-dir collection of a previous run and retries after PENDING.

Read only the evidence you need. This example needs stdout, so it also works
with older aggregate-only records that lack individual execution.json files.
See the [execution contract](Execution_Contract.md) for supported JSON fields
and the original-environment restriction on these paths.

The sample's policies are explicit:
- Missing stdout, absent/multiple distinct locations or a relative location:
  final ERROR, because the sample cannot identify the external execution.
- Known location without result.txt: PENDING; collecting again retries it.
- Completed verdict file: PASS, FAIL, ERROR or SKIP.
- Unexpected I/O error: collector exits nonzero, yielding a retryable collection
  error. This is different from a final ERROR verdict.

An asynchronous real system needs its own completion rule. The mere existence
of a log does not imply completion, and an execution return code is not itself
the test verdict.

## Cleanup

After all activity has stopped, optionally remove only this sample's data:

    rm -rf -- work/collector-from-log runs/collector-from-log work/log-location-results

No cleanup runs automatically. These directories include all runs of this sample.
