# Architecture

## Purpose

`mockingbird` is a small regression **orchestrator**. It is not a simulator wrapper,
test framework, SCM client, or farm scheduler.

## Design philosophy

The most important architectural rule is:

> **Mockingbird does not understand the system it orchestrates.**

The core should remain small and boring. System-specific knowledge belongs
outside the core, and abstractions should be introduced only after real repeated
use shows that they are common. Simplicity is a maintenance feature, not a lack
of ambition.

This follows a Unix-like design preference: narrow responsibilities, explicit
interfaces, plain evidence, and components that can be replaced independently.

See `Design_Principles.md`.

Its generic lifecycle is:

```text
regression.yaml
      |
   doctor        optional, non-destructive connection checks
      |
   prepare  ---- SourceProvider ----> materialized sources
      |
 context.json
      |
    setup   ---- ExecutionAdapter ---> project setup
      |
    plan    <--- ExecutionAdapter ---- canonical Jobs
      |
  plan.json
      |
 select / dry-run
      |
     run    ---- CapacityProvider ---> current concurrency allowance
      |      ---- ExecutionAdapter ---> project execution
      |
 run.json + executions.json
      |
   collect  <--- ExecutionAdapter ---- project interpretation
      |
 result.json
```

The durable evidence chain remains:

```text
Context -> Plan -> Run -> Result
```

## Core responsibility

Core may know:

- lifecycle ordering;
- canonical `Job`, `ExecutionContext`, `JobExecution`, and `TestResult` models;
- ID-based selection;
- generic concurrency and polling;
- per-job directory allocation;
- evidence persistence;
- plugin loading/contracts;
- connection-check orchestration.

Core must not know:

- how VCS/QEMU/board/formal tools are started;
- what a testcase command means;
- how project PASS/FAIL is extracted;
- Git/SVN command semantics;
- LSF/Slurm/proprietary farm semantics.

Concrete behavior remains behind three boundaries:

```text
ExecutionAdapter
SourceProvider
CapacityProvider
```

## ExecutionAdapter

```python
probe(context) -> list[CheckResult]
setup(context)
plan(context) -> list[Job]
execute(context, job, execution_context) -> JobExecution
collect(context, executions) -> list[TestResult]
```

`Job.payload` and `JobExecution.observation` are opaque to core.

### Collection and heterogeneous evidence

Collection is project interpretation, not core interpretation.

```text
Execution
   |
   +-- arbitrary project files / observations
   |
   v
project-owned collect()
   |
   +-- determines canonical result
   |
   v
TestResult
   |
   v
Mockingbird persists association/provenance
```

A trivial command may expose only logs and a return code. VCS may expose a
simulation log, FSDB, Tarmac, coverage data, or other outputs. Other tools may
produce completely different evidence.

Mockingbird does not define what those artifacts mean and does not require them
to fit a common taxonomy. The collector may return project-specific reason or
metadata when useful, but core treats such information as opaque.

The architectural requirement is traceability: a recorded result remains
associated with its Job/Execution and with project-owned evidence references
that the integration chooses to preserve. Traceability does not imply that core
understands or validates the evidence.

### Job

A Job is the smallest independently schedulable and useful rerunnable unit. It
is not necessarily one testcase. The project decides the granularity.

Core requires IDs to be unique, non-empty, free of control characters, and
stable enough to support selection/rerun semantics. Stability across runs is a
project contract and is checked by the conformance kit under a fixed context.

### ExecutionContext

Core creates one isolated filesystem context per selected Job:

```text
runs/<run-id>/jobs/<safe-id>/
  work/
  artifacts/
  logs/
    stdout.log
    stderr.log
```

The adapter receives these paths but owns all project behavior inside them.
Core records only generic relative path evidence.

## Adapter process utility

`mockingbird.adapter_utils.run_process` is provided for adapter authors. It is not
part of core scheduling semantics. It standardizes the safe/default subprocess
pattern:

```text
shell=False
stdin=DEVNULL
stdout/stderr -> files
start_new_session=True
timeout -> process-group SIGTERM -> grace -> SIGKILL
```

This avoids buffering large simulator logs in memory or canonical JSON.

## SourceProvider

```python
probe(source) -> list[CheckResult]
materialize(source, destination) -> resolved_evidence
```

Git and SVN are bundled implementations. Any number and mixture of sources is
allowed in one regression context.

## CapacityProvider

```python
probe() -> list[CheckResult]
available_slots() -> int
```

The scheduler computes:

```text
effective_limit = min(max_parallel, available_slots())
```

No queue/farm semantics enter core.

## Connection diagnostics

`mockingbird doctor` validates the definition, loads every configured plugin, and runs
non-destructive provider/adapter probes. It does not prepare sources or run jobs.

The reusable `mockingbird.testing` conformance kit separately verifies implementation
contracts for project-side pytest suites.

## Project-owned extensions

Projects should normally not edit mockingbird core. Install a project package and
reference it using `module:Class`:

```yaml
execution:
  adapter: my_soc_verification.regression:Adapter
```

The same external-plugin form is supported for source and capacity providers.

## Architecture enforcement

Tests enforce that:

- core modules do not import concrete adapters/source/capacity providers;
- core modules do not spawn project subprocesses;
- extension signatures remain deliberate;
- project plugins load without core edits;
- per-job execution contexts are isolated;
- process utility streams logs and terminates timed-out process groups;
- doctor reports connection failures without preparing a context;
- required architecture/ADR documents remain present.

See `Architecture_Contract.md`, `Adapter_Implementation_Guide.md`, and
`Adapter_Conformance_Testing.md`.
