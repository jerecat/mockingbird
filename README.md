# regorch

A deliberately small, adapter-driven regression orchestrator prototype.

Current prototype version: **0.4.0**.

Core owns **when** to prepare, setup, plan, select, schedule, run, and collect.
It does not know how VCS/QEMU/a board/formal tool starts, what a testcase command
means, how project PASS/FAIL is parsed, whether sources are Git/SVN, or how a
compute farm measures load.

```text
regression.yaml
      |
    doctor             non-destructive connection check
      |
   prepare  --> context.json
      |
    setup
      |
     plan   --> plan.json
      |
 select / dry-run
      |
     run    --> run.json + executions.json + per-job work/log/artifact dirs
      |
   collect  --> result.json
```

The evidence model remains:

```text
Context -> Plan -> Run -> Result
```

## Key architecture rules

1. Core never interprets project commands.
2. Core never knows Git/SVN command semantics.
3. Core never knows farm/queue semantics.
4. A `Job` is the project-chosen independently schedulable/rerunnable unit.
5. FAIL rerun granularity is Job granularity.
6. Core creates an isolated `ExecutionContext` per selected Job.
7. Large stdout/stderr belongs in files, not Python memory or canonical JSON.
8. Project integration should not require editing/forking core.
9. `reg doctor` and project-side conformance tests are first-class integration gates.
10. Architecture rules are executable tests and documented ADRs.

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
reg doctor examples/sanity-linux.yaml
reg all examples/sanity-linux.yaml
```

Or:

```bash
make architecture
make doctor
make sanity
make self-demo
```

## Workspace/run layout

Relative paths are based on the directory where `reg` is invoked.

```text
$PWD/
  regression.yaml
  work/
    sources/
    exec/
    .reg/
      context.json
      plan.json
      state.json
  runs/
    <run-id>/
      context.json
      plan.json
      run.json
      executions.json
      result.json
      jobs/
        <safe-job-directory>/
          work/
          artifacts/
          logs/
            stdout.log
            stderr.log
```

Job IDs are never trusted directly as filesystem paths; core allocates a safe,
deterministic directory name per selected Job.

## Lifecycle

```bash
reg doctor regression.yaml
reg prepare regression.yaml
reg setup regression.yaml
reg plan regression.yaml
reg dry-run regression.yaml
reg run regression.yaml --interactive
reg collect regression.yaml
reg status regression.yaml
```

Or:

```bash
reg all regression.yaml --interactive
```

`doctor` does not materialize sources or run Jobs. It validates configuration,
plugin loading, and configured connection probes.

## Job model

A Job is **not necessarily one testcase**. Examples:

```text
1 C testcase
1 UVM test + seed
100-test batch
formal property group
board boot + scenario
compile/elaboration unit
```

Choose the boundary such that rerunning the same Job ID is meaningful. If one Job
contains 100 tests, `--failed-from` reruns that whole Job.

Job IDs should be stable and human-readable. Do not embed timestamp/PID/run path.

## Selection

```bash
reg run regression.yaml --test pcie/dma/write/seed-001
reg run regression.yaml --match 'pcie/*'
reg plan regression.yaml --write-selection run.txt
vim run.txt
reg run regression.yaml --selection run.txt
reg run regression.yaml --failed-from runs/<explicit-run>/result.json
```

There is intentionally no implicit "latest failed" source.

## Adapter process execution

For normal Linux subprocess adapters, use:

```python
from regorch.adapter_utils import run_process

process = run_process(
    ["./run_test.sh", "--test", job.id],
    execution,
    timeout_s=3600,
    env=my_environment,
)
```

The utility uses:

```text
shell=False
stdin=DEVNULL
stdout/stderr streamed directly to files
new process session
timeout -> SIGTERM -> grace -> SIGKILL for the process group
```

Avoid `capture_output=True` for real regression payloads. Simulator logs can be
large; `JobExecution`/`result.json` should contain paths and small metadata only.

If shell behavior is required, place it in a project-owned wrapper script rather
than embedding shell strings in generic Python.

## Connection and conformance

Runtime/machine health:

```bash
reg doctor regression.yaml
```

Implementation contract in project pytest:

```python
from regorch.testing import assert_conformance, check_execution_adapter

checks = check_execution_adapter(MyAdapter(), project_context, tmp_path)
assert_conformance(checks)
```

Equivalent helpers exist for SourceProvider and CapacityProvider.

## Extension contracts

```python
ExecutionAdapter:
  probe(context)
  setup(context)
  plan(context) -> list[Job]
  execute(context, job, execution_context) -> JobExecution
  collect(context, executions) -> list[TestResult]

SourceProvider:
  probe(source)
  materialize(source, destination) -> resolved_evidence

CapacityProvider:
  probe()
  available_slots() -> int
```

Built-ins use short names. Project-owned plugins can be installed separately:

```yaml
execution:
  adapter: my_soc_verification.regression:Adapter
```

## Documentation

Start here:

- `Documentation/Architecture.md`
- `Documentation/Architecture_Contract.md`
- `Documentation/Adapter_Implementation_Guide.md`
- `Documentation/Adapter_Conformance_Testing.md`
- `Documentation/Getting_Started.md`
- `Documentation/Integration_Guide.md`
- `Documentation/Demos.md`
- `Documentation/ADR/`
