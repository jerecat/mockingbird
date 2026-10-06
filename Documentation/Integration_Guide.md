# Integration Guide

## What normally changes for a new verification environment?

There are four possible integration points. Most projects need only the first two rows.

| Area | Usually needed? | Where it belongs |
|---|---:|---|
| regression definition | yes | project-owned `regression.yaml` |
| execution behavior | yes | project-owned `ExecutionAdapter` package |
| source acquisition | usually no | built-in Git/SVN, or custom `SourceProvider` |
| load/capacity query | sometimes | built-in command provider, or custom `CapacityProvider` |

**Do not edit lifecycle, scheduler, selection, or canonical result code just to connect a project.**

## Step 1: Describe sources and generic policy

```yaml
name: soc-nightly

sources:
  - name: dut
    provider: git
    url: ssh://server/dut.git
    revision: main

  - name: testbench
    provider: svn
    url: https://server/svn/tb/trunk
    revision: "HEAD"

execution:
  adapter: my_soc_regression.adapter:Adapter
  config:
    profile: nightly

scheduler:
  capacity_provider: command
  max_parallel: 8
  poll_interval_s: 5.0
  config:
    command: ["my-capacity-wrapper"]
```

At `prepare`, symbolic source revisions are frozen into concrete evidence.

## Step 2: Implement an ExecutionAdapter outside this repository

Create a normal Python package in the project repository:

```text
my-soc-regression/
  pyproject.toml
  src/
    my_soc_regression/
      __init__.py
      adapter.py
```

`adapter.py`:

```python
from regorch.contracts import ExecutionAdapter
from regorch.models import Job, JobExecution, TestResult

class Adapter(ExecutionAdapter):
    def setup(self, context):
        ...

    def plan(self, context):
        return [Job(id="test_001", payload={"anything": "project-owned"})]

    def execute(self, context, job):
        ...
        return JobExecution(...)

    def collect(self, context, executions):
        ...
        return [TestResult(id="test_001", status="PASS")]
```

Install it in the same virtual environment:

```bash
pip install -e /path/to/my-soc-regression
```

Then reference it without modifying regorch:

```yaml
execution:
  adapter: my_soc_regression.adapter:Adapter
```

A complete minimal external example is under `examples/external_adapter/`.

## Adapter responsibilities

### setup

Prepare project-owned execution prerequisites. Examples might include build setup, environment generation, or a project command that prepares a testbench.

Core does not interpret the operation.

### plan

Return canonical `Job` objects. The only field core interprets is `Job.id` for selection and evidence. `payload` is project-owned and JSON-serializable.

### execute

Execute one selected `Job` and return raw `JobExecution` evidence. `observation` is opaque to core.

### collect

Interpret execution observations and normalize them into `TestResult` with one of:

```text
PASS
FAIL
ERROR
SKIP
```

This is where project-specific result parsing belongs.

## SourceProvider: only when Git/SVN are insufficient

Built-ins support any number and mixture of Git and SVN sources. If another materialization mechanism is needed, implement:

```python
from regorch.contracts import SourceProvider

class Provider(SourceProvider):
    def materialize(self, source, destination):
        ...
        return {"resolved_revision": "..."}
```

Reference it with:

```yaml
provider: company_sources.internal:Provider
```

## CapacityProvider: often a wrapper command is enough

Before writing Python, prefer the generic command provider. The command only needs to print one non-negative integer:

```text
3
```

That means "this orchestrator may currently have at most 3 jobs running".

Only implement a custom provider if that tiny command boundary is insufficient.

## Integration checklist

Before using a new adapter in a real regression:

```text
[ ] setup is idempotent enough for repeated orchestration
[ ] plan returns stable unique IDs
[ ] job payload is JSON-serializable
[ ] execute returns one JobExecution per submitted Job
[ ] collect returns exactly one TestResult per execution
[ ] collect uses only canonical statuses
[ ] secrets are not written into YAML/context evidence
[ ] source revisions needed for reproduction are frozen by prepare
[ ] a dry-run clearly shows the selected jobs before execution
[ ] project adapter tests exist outside core tests
```
