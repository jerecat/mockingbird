# Integration Guide

## What a project normally owns

| Area | Usually needed? | Owner |
|---|---:|---|
| regression definition | yes | project `regression.yaml` |
| execution behavior | yes | project `ExecutionAdapter` package |
| adapter tests | yes | project pytest suite using `mockingbird.testing` |
| source acquisition | usually no | built-in Git/SVN or custom SourceProvider |
| capacity query | sometimes | command provider or custom CapacityProvider |

Do not edit lifecycle, scheduler, selection, or canonical result code merely to
connect a project.

## 1. Define sources and scheduling policy

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
    revision: HEAD

execution:
  adapter: my_soc_regression.adapter:Adapter
  config:
    profile: nightly

scheduler:
  capacity_provider: command
  max_parallel: 8
  poll_interval_s: 5.0
  config:
    command: [my-capacity-wrapper]
```

## 2. Implement the project adapter

```python
from mockingbird.contracts import ExecutionAdapter
from mockingbird.models import CheckResult, Job, JobExecution, TestResult
from mockingbird.adapter_utils import run_process

class Adapter(ExecutionAdapter):
    def probe(self, context):
        return [CheckResult("execution", "tool", "PASS", "tool reachable")]

    def setup(self, context):
        ...

    def plan(self, context):
        return [Job(id="pcie/dma/write/seed-001", payload={...})]

    def execute(self, context, job, execution):
        process = run_process(
            ["./run_test.sh", job.id],
            execution,
            timeout_s=3600,
        )
        return JobExecution(
            job_id=job.id,
            started_at="...",
            finished_at="...",
            duration_s=process.duration_s,
            observation=process.to_observation(),
        )

    def collect(self, context, executions):
        ...
```

See `Adapter_Implementation_Guide.md` for stdout/stderr, timeout, Job identity,
and result-status guidance.

## 3. Add project-side conformance tests

```python
from mockingbird.testing import assert_conformance, check_execution_adapter


def test_mockingbird_adapter(tmp_path, project_context):
    checks = check_execution_adapter(MyAdapter(), project_context, tmp_path)
    assert_conformance(checks)
```

This is expected integration work, not optional polish. Run it before the adapter
is accepted into a nightly regression environment.

## 4. Run doctor on the actual machine

```bash
mockingbird doctor regression.yaml
```

This catches missing tools, repository access problems, adapter probe failures,
and capacity query failures before source materialization or regression start.

## 5. Validate the plan

```bash
mockingbird prepare regression.yaml
mockingbird setup regression.yaml
mockingbird plan regression.yaml
mockingbird dry-run regression.yaml
```

Check that Job IDs are stable and that the chosen Job granularity matches the
rerun granularity the team wants.

## 6. Capacity integration

Prefer the command provider first. The wrapper prints one non-negative integer:

```text
3
```

Only write a custom CapacityProvider if that boundary is insufficient.

## 7. Source integration

Built-in Git/SVN can be mixed in arbitrary count. Implement a custom
SourceProvider only for a materially different source materialization mechanism.

## Integration acceptance checklist

```text
[ ] mockingbird doctor passes on a representative execution machine
[ ] project adapter conformance pytest passes
[ ] setup can be repeated safely
[ ] plan returns stable unique Job IDs
[ ] Job granularity matches desired rerun granularity
[ ] Job payloads are JSON serializable
[ ] large stdout/stderr goes to files, not Python memory/JSON
[ ] timeout/process-group behavior is defined
[ ] shell=True is not used; shell policy lives in project wrapper scripts
[ ] collect distinguishes FAIL from infrastructure ERROR
[ ] secrets are absent from context/result/check messages
[ ] source revisions needed for reproduction are frozen by prepare
[ ] dry-run clearly shows intended selection before execution
```
