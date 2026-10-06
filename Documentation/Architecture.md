# Architecture

## Purpose

`regorch` is a small regression **orchestrator**, not a simulator wrapper, test framework, source-control client, or farm scheduler.

Its job is to preserve and execute one generic lifecycle:

```text
human intent
regression.yaml
      |
      v
   PREPARE  ---- SourceProvider ----> materialized sources
      |
      v
 context.json
      |
      v
    SETUP   ---- ExecutionAdapter ---> project-owned setup
      |
      v
    PLAN    <--- ExecutionAdapter ---- opaque jobs
      |
      v
  plan.json
      |
      v
  SELECT / DRY-RUN
      |
      v
     RUN    ---- CapacityProvider ---> current slot allowance
      |      ---- ExecutionAdapter ---> concrete execution
      v
 run.json + executions.json
      |
      v
   COLLECT  <--- ExecutionAdapter ---- project-specific interpretation
      |
      v
 result.json
```

The durable evidence chain is:

```text
Context -> Plan -> Run -> Result
```

## Core responsibility

Core may know:

- lifecycle ordering;
- canonical `Job`, `JobExecution`, and `TestResult` models;
- ID-based selection;
- concurrency and polling mechanics;
- evidence persistence;
- generic plugin contracts.

Core must not know:

- how VCS, QEMU, a board, or another execution target starts;
- what a testcase command means;
- how PASS/FAIL is found in project logs;
- Git or SVN command semantics;
- LSF, Slurm, proprietary farm, or host-load semantics.

Those details belong behind contracts.

## Extension boundaries

### ExecutionAdapter

```python
setup(context)
plan(context) -> list[Job]
execute(context, job) -> JobExecution
collect(context, executions) -> list[TestResult]
```

The `Job.payload` and `JobExecution.observation` fields are opaque to core.

### SourceProvider

```python
materialize(source, destination) -> resolved_evidence
```

Built-ins currently include Git and SVN. A regression may contain any number and mixture of sources.

### CapacityProvider

```python
available_slots() -> int
```

The scheduler only computes:

```text
effective_limit = min(max_parallel, available_slots())
```

## Project-owned extensions

A project should normally **not edit regorch core**. Install its own Python package and reference a class with `module:Class`:

```yaml
execution:
  adapter: my_soc_verification.regression:Adapter
```

The same form is supported for source and capacity providers when the built-ins are insufficient.

Short names such as `demo_linux`, `git`, `svn`, and `fixed` resolve to bundled plugins.

## Workspace boundary

By default, relative workspace paths are based on the directory from which `reg` is invoked:

```text
$PWD/
  regression.yaml
  work/
    sources/
    exec/
    .reg/
  runs/
```

This makes the invocation directory the physical boundary of one regression workspace while keeping repository locations declarative.

## Architecture enforcement

The architecture is executable, not only documented. The test suite checks:

- root/core modules do not import concrete adapter/source/capacity implementations;
- root/core modules do not execute project commands directly;
- extension contracts retain their deliberately small method surfaces;
- bundled plugins implement the declared contracts;
- external `module:Class` plugins load without modifying core;
- required architecture and ADR documents remain present.

See `Documentation/Architecture_Contract.md` and `tests/test_architecture_contracts.py`.
