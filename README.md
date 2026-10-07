# Mockingbird

A deliberately small, contract-driven regression orchestrator prototype.

Current prototype version: **0.5.0**.

## Design philosophy

**Mockingbird should not understand the system it orchestrates.**

Keep the core small, keep system-specific knowledge outside it, and prefer the
simplest implementation that satisfies the requirement. A boring tool is easier
to inspect, debug, replace, and maintain — this is intentional and Unix-inspired.

Before adding a feature to core, ask:

> Does Mockingbird itself need to know this?

If not, it belongs in an adapter, provider, project wrapper, or external command.
Generalize only after the same real problem appears repeatedly.

See `Documentation/Design_Principles.md`.

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


## Normal project integration: write the contract

Projects that already have a command-line entry point should not need
Mockingbird Python code.

```yaml
execution:
  command: ["./run.sh"]
  timeout_s: 600
  jobs:
    - test_a
    - test_b
  collect:
    mode: no-check
```

A string Job runs as `./run.sh <job-id>`. Defaults are expanded and validated
by plan; each Job can override command, args, timeout, and collect. no-check is
also the implicit default and does not verify success. Configure a project-owned
collector when result judgement is needed. Repeated collect retries only
unresolved Jobs in the same run.

See `Documentation/Execution_Contract.md`.

Normal operation is serial (`max_parallel: 1`): the next command starts after
the previous command returns and capacity permits dispatch. Bundled examples
follow this policy. Configuration and runtime reject any max_parallel value
other than the integer 1; omission defaults to 1. See ADR 0009.

## Key architecture rules

1. Core never interprets project commands.
2. Core never knows Git/SVN command semantics.
3. Core never knows farm/queue semantics.
4. A `Job` is the project-chosen independently schedulable/rerunnable unit.
5. FAIL rerun granularity is Job granularity.
6. Core creates an isolated `ExecutionContext` per selected Job.
7. Large stdout/stderr belongs in files, not Python memory or canonical JSON.
8. Project integration should not require editing/forking core.
9. `mockingbird doctor` and project-side conformance tests are first-class integration gates.
10. Architecture rules are executable tests and documented ADRs.

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
mockingbird doctor examples/sanity-linux.yaml
mb all examples/sanity-linux.yaml
```

The installed CLI has two equivalent entry points:

```bash
mockingbird --help
mb --help
```

`mb` is a short alias registered by `pyproject.toml`; it is not a shell-only alias.

Or:

```bash
make architecture
make doctor
make sanity
make self-demo
```

## Workspace/run layout

Relative paths are based on the directory where `mockingbird` is invoked.

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
      collection.json
      result.json
      jobs/
        <safe-job-directory>/
          execution.json
          collection.json
          work/
          artifacts/
          logs/
            stdout.log
            stderr.log
```

Job IDs are never trusted directly as filesystem paths; core allocates a safe,
deterministic directory name per selected Job.

For new runs, per-Job execution/collection files are the recovery checkpoints;
run-level JSON files are derived views. A failed prepare blocks setup/plan/run
until prepare succeeds again. Do not overlap prepare/setup/run in one workspace.
See [ADR 0010](Documentation/ADR/0010-checkpoint-ownership-and-prepare-validity.md).

## Lifecycle

Prepare acquires sources only when no checkout exists. Existing Git/SVN working
trees are reused without updates or deletion, including local edits and build
outputs. To change revisions, use Git/SVN yourself or choose a new workspace.
Recorded revisions are prepare-time metadata, not snapshots of source contents.
Mockingbird does not track edits made before or during run. See
[ADR 0011](Documentation/ADR/0011-reuse-user-managed-source-trees.md).

```bash
mockingbird doctor regression.yaml
mockingbird prepare regression.yaml
mockingbird setup regression.yaml
mockingbird plan regression.yaml
mockingbird dry-run regression.yaml
mockingbird run regression.yaml --interactive
mockingbird collect regression.yaml
mockingbird status regression.yaml
```

Or:

```bash
mockingbird all regression.yaml --interactive
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
mockingbird run regression.yaml --test pcie/dma/write/seed-001
mockingbird run regression.yaml --match 'pcie/*'
mockingbird plan regression.yaml --write-selection run.txt
vim run.txt
mockingbird run regression.yaml --selection run.txt
mockingbird run regression.yaml --failed-from runs/<explicit-run>/result.json
```

There is intentionally no implicit "latest failed" source.

## Advanced Python adapter process execution

Normal users should use the declarative execution contract above. For a custom
Python adapter that genuinely needs direct subprocess control, use:

```python
from mockingbird.adapter_utils import run_process

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
mockingbird doctor regression.yaml
```

Custom Python plugin implementation contract in project pytest:

```python
from mockingbird.testing import assert_conformance, check_execution_adapter

checks = check_execution_adapter(MyAdapter(), project_context, tmp_path)
assert_conformance(checks)
```

Equivalent helpers exist for SourceProvider and CapacityProvider.

## Advanced extension contracts

The declarative command contract is the normal execution path. Python extension
contracts remain available as escape hatches:

```python
ExecutionAdapter:
  probe(context)
  setup(context)
  plan(context) -> list[Job]
  execute(context, job, execution_context) -> JobExecution
  collect(context, executions) -> list[TestResult | CollectionAttempt]

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
- `Documentation/Execution_Contract.md`
- `Documentation/Architecture_Contract.md`
- `Documentation/Adapter_Implementation_Guide.md`
- `Documentation/Adapter_Conformance_Testing.md`
- `Documentation/Getting_Started.md`
- `Documentation/Integration_Guide.md`
- `Documentation/Demos.md`
- `Documentation/ADR/`
