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
    setup   ---- command list, then ExecutionAdapter hook ---> project setup
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
Confirmed plan (including context) -> Run -> Result
```

## Core responsibility

Core may know:

- lifecycle ordering;
- canonical `Job`, `ExecutionContext`, `JobExecution`, `CollectionAttempt`, and `TestResult` models;
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

The normal user-facing execution path is declarative. `execution.command`,
Jobs, timeout, and collection policy are normalized internally to the built-in
command ExecutionAdapter. Users do not normally implement Python.

Custom Python ExecutionAdapter remains an advanced escape hatch.

## ExecutionAdapter

```python
probe(context) -> list[CheckResult]
setup(context)
plan(context) -> list[Job]
execute(context, job, execution_context) -> JobExecution
collect(context, executions) -> list[TestResult | CollectionAttempt]
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

The result envelope has one deliberately small contract:

```text
TestResult
  id          Mockingbird Job ID
  status      PASS | FAIL | ERROR | SKIP
  artifacts   list[str]
```

`artifacts` is a list of opaque references supplied by the project collector.
A reference will often be a path, but Mockingbird does not require it to be a
path, does not classify it, and does not derive the result from it. An empty list
is valid.

The architectural requirement is traceability: a recorded result remains
associated with its Job/Execution and with the opaque artifact references the
integration chooses to preserve. Traceability does not imply that core
understands or validates the referenced evidence.

### Job

A Job is the smallest independently schedulable and useful rerunnable unit. It
is not necessarily one testcase. The project decides the granularity.

Core requires IDs to be unique, non-empty, free of control characters, and
stable enough to support selection/rerun semantics. Stability across runs is a
project contract and is checked by the conformance kit under a fixed context.

### ExecutionContext

Core creates one isolated filesystem context per selected Job:

```text
work/<plan>/runs/<run-id>/jobs/<safe-id>/
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

Core supplies the saved project directory as `source['_invocation_dir']` to
probe/materialize. Providers can resolve relative source inputs against it without
changing the MB process cwd. It is runtime context, not a required YAML field.
Built-in providers preserve this base when prepare/doctor is called elsewhere.

Git and SVN are bundled implementations. Any number and mixture of sources is
allowed in one regression context.

## CapacityProvider

```python
probe() -> list[CheckResult]
available_slots() -> int
```

The scheduler uses `available_slots()` as a hard dispatch gate together with
`max_parallel`. Existing executions are not killed if capacity falls, but no
new execution is admitted until the gate permits it again.

For asynchronous external hand-off, the CapacityProvider must account for work
already submitted outside Mockingbird in later samples. Core does not track
external scheduler Job IDs.

No queue/farm semantics enter core.

## Connection diagnostics

`mockingbird doctor` validates the definition, loads every configured plugin, and runs
non-destructive provider/adapter probes. It does not prepare sources or run jobs.

The reusable `mockingbird.testing` conformance kit separately verifies implementation
contracts for project-side pytest suites.

## Project integration and advanced extensions

Projects should normally not edit Mockingbird core or write a Python execution
adapter. Start with the declarative command contract in
`Execution_Contract.md`.

If that boundary is genuinely insufficient, install a project package and
reference a Python `module:Class` adapter. The same external-plugin form is
available for source and capacity providers.

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

See `Architecture_Contract.md`, `Execution_Contract.md`,
`Adapter_Implementation_Guide.md`, and `Adapter_Conformance_Testing.md`.


## Resolved contracts and collection cycles

Configuration and runtime enforce max_parallel: 1, as recorded in ADR 0009.
Parallel execution is disabled; enabling it later requires revisiting that ADR.

Plan expands defaults into full per-Job command/args/timeout/collect payloads,
validates, and freezes them. Missing collect becomes no-check. Dispatch remains
list-ordered and capacity-gated; there is no dependency graph.

Execution records are saved per Job as they return. Collection state is distinct
from execution evidence and final TestResult. CollectionAttempt carries PENDING
or ERROR when no final judgement is available. Repeated collect checkpoints
only unresolved Jobs; final results remain unchanged. Job-level execution.json
and collection.json are authoritative checkpoints. Run-level executions.json,
collection.json and result.json are derived views, not recovery inputs for new
runs. An incomplete selected set has aggregate status PENDING, never PASS.
See ADR 0008 and ADR 0010 for checkpoint ownership and legacy compatibility.

Declarative setup and failure invalidation are defined by
[ADR 0012](ADR/0012-declarative-setup-and-retry.md). The standard command adapter
requires no setup cycle when its top-level setup list is empty or omitted.

## Named plans

ADR 0014 defines plan-name identity and explicit confirmation. MB derives the
workspace/run layout from the name; run consumes the entire saved plan without
reading live YAML. A run retains its own plan, so replanning can proceed while
an older run executes. See [Named plans](Named_Plans.md).
