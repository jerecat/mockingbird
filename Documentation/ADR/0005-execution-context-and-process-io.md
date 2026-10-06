# ADR 0005: Per-job ExecutionContext and streamed process I/O

Status: Accepted

## Context

Real regression jobs may emit gigabytes of simulator or firmware logs. Capturing
stdout/stderr into Python strings or canonical JSON creates avoidable memory
pressure and makes long-running jobs fragile. Different adapters also tended to
invent their own work-directory and timeout conventions.

## Decision

Core allocates a generic `ExecutionContext` for every selected `Job`:

```text
runs/<run-id>/jobs/<stable-directory>/
  work/
  artifacts/
  logs/
    stdout.log
    stderr.log
```

The adapter receives that context in:

```python
execute(context, job, execution_context)
```

Core still does not know what command or simulator is executed.

A reusable adapter utility, `regorch.adapter_utils.run_process`, is provided with
these defaults/contracts:

- `shell=False` only;
- `stdin=DEVNULL`;
- stdout/stderr streamed directly to files;
- no full stdout/stderr body in `JobExecution` or canonical JSON;
- optional timeout;
- timeout termination is process-group `SIGTERM`, grace period, then `SIGKILL`;
- per-job working directory by default.

If shell syntax is required, the project should own a wrapper script and execute
that script explicitly.

## Consequences

Large logs do not accumulate in orchestrator memory. Every job has predictable
filesystem isolation. Adapter implementations share one recommended process
pattern without moving project execution semantics into core.
