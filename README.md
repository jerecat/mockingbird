# regorch

A deliberately small, adapter-driven regression orchestrator prototype.

Current prototype version: **0.3.0**.

The core knows **when** to prepare, setup, plan, select, schedule, run, and collect. It does **not** know how a simulator starts, how a board is controlled, what a test command means, which source-control system is used, or how a compute farm reports load.

The main evidence chain is:

```text
regression.yaml                 human-authored intent
       |
       v
   prepare  -- SourceProvider(s) --> work/sources/*
       |
       v
 context.json                   frozen verification context
       |
     setup                      project-specific adapter boundary
       |
       v
      plan  <------------------- adapter discovers opaque Jobs
       |
       v
   plan.json
       |
     select                     core operates on Job IDs only
       |
       v
      run   -- CapacityProvider --> generic scheduler
       |
       v
    run.json + executions.json
       |
    collect <------------------- adapter interprets observations
       |
       v
   result.json                   canonical result evidence
```

In short:

```text
Context -> Plan -> Run -> Result
```

`dry-run` is a read-only view of the frozen context + selected plan before `run`.

## Design rules

1. **Core never interprets project commands.** Job payloads are opaque JSON-serializable values.
2. **Core never knows Git/SVN semantics.** Source materialization is behind `SourceProvider`.
3. **Core never knows farm/queue semantics.** Capacity is behind `CapacityProvider`.
4. **Human intent and machine evidence are separate.** YAML is input; JSON is frozen evidence.
5. **FAIL rerun is explicit.** There is no implicit "previous run" selector.
6. **Every run snapshots its context and plan.** A result can be traced back to exactly what was selected and executed.
7. **Project integration does not require a core fork.** External plugins can be installed separately and referenced as `module:Class`.
8. **Architecture rules are executable contracts.** Boundary tests fail if concrete execution/SCM/load semantics leak into core.

## Repository layout

```text
src/regorch/
  cli.py
  context.py              workspace + frozen context
  lifecycle.py            prepare/setup/plan/run/collect lifecycle
  selection.py            ID-only selection logic
  scheduler.py            generic parallel scheduler
  contracts.py            extension contracts
  models.py               canonical Job/Execution/Result models
  sources/
    git.py                 Git SourceProvider
    svn.py                 SVN SourceProvider
  capacity/
    fixed.py               fixed concurrency provider
    command.py             command-backed concurrency provider
  adapters/
    demo_linux.py          demo only: ls/mkdir/rm/sh commands

tests/                     unit + architecture-contract + end-to-end tests
Documentation/             architecture, integration guides, and ADRs
examples/                  Linux sanity, self-host, external-plugin demos
```

The demo Linux commands exist only under the demo adapter/config. The core does not know their meaning.

## Development setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

For environments that prefer requirements files:

```bash
pip install -r requirements-dev.txt
pip install -e .
pytest
```

Fast checks after installation:

```bash
make architecture   # architecture contract tests
make sanity         # ordinary Linux commands, no project integration
make self-demo      # regorch orchestrates selected tests of regorch itself
```

## Workspace convention

Relative `workspace` and `run_root` paths are resolved from the directory where `reg` is invoked.

With the default paths:

```text
$PWD/
  regression.yaml
  work/
    sources/
      <source-name>/          materialized source trees
    exec/                     adapter-owned execution work area
    .reg/
      context.json
      plan.json
      state.json
      last_run.json
      last_result.json
  runs/
    <run-id>/
      context.json
      plan.json
      run.json
      executions.json
      result.json
```

`work/sources/*` is tool-owned. Git materialization cleans stale files so the tree matches the resolved commit.

## Lifecycle

Run each stage explicitly:

```bash
reg prepare regression.yaml
reg setup regression.yaml
reg plan regression.yaml
reg dry-run regression.yaml
reg run regression.yaml --interactive
reg collect regression.yaml
reg status regression.yaml
```

Or use the convenience chain:

```bash
reg all regression.yaml --interactive
```

`--interactive` is a **single pre-run checklist**, not a question per testcase. It shows the frozen context, resolved source revisions, selected job count/IDs, and scheduler settings, then asks once before execution.

`collect` and `all` return a non-zero process exit code when the canonical regression result is not PASS, which makes them usable from CI.

## Verification context / source materialization

A regression may contain zero, one, or any number of mixed sources:

```yaml
sources:
  - name: dut
    provider: git
    url: ssh://server/dut.git
    revision: main

  - name: testbench
    provider: svn
    url: https://server/svn/tb/trunk
    revision: "18291"

  - name: firmware
    provider: git
    url: ssh://server/fw.git
    revision: release/r1
```

At `prepare`, symbolic revisions are resolved and frozen into `work/.reg/context.json`:

```text
requested revision      frozen evidence
------------------      ---------------
main                 -> Git commit SHA
release/r1           -> Git commit SHA
HEAD / SVN revision  -> concrete SVN revision
```

Provider-specific non-secret options may be placed under a source `config` mapping and are preserved in the context. Credentials/tool installation remain external environment concerns and should not be written into the context.

The intent is that `context.json` contains the orchestrator-controlled information needed to reconstruct the verification context later.

## Planning and test selection

The adapter discovers jobs. Core sees only canonical IDs plus an opaque payload:

```text
Adapter -> Job(id, opaque_payload) -> Plan -> Selection -> Scheduler -> Adapter
```

### All tests

```bash
reg run regression.yaml
```

### Exact IDs

```bash
reg run regression.yaml \
  --test mkdir_demo \
  --test list_demo
```

### ID glob

```bash
reg run regression.yaml --match '*demo'
```

### Editable selection file

Generate a plain text selection from the canonical plan:

```bash
reg plan regression.yaml --write-selection run.txt
vim run.txt
reg run regression.yaml --selection run.txt
```

The file contains only opaque job IDs, one per line. Blank lines and `#` comments are ignored. Editing the selection never requires core to understand testcase commands.

### Rerun FAIL from a specific prior result

There is intentionally no implicit "last failed" behavior. Point at the exact evidence to use:

```bash
reg run regression.yaml \
  --failed-from runs/20261007_010203_000000_my-regression/result.json
```

A run directory may also be supplied:

```bash
reg run regression.yaml \
  --failed-from runs/20261007_010203_000000_my-regression
```

Only tests whose prior canonical status is exactly `FAIL` are selected. The new `run.json` records:

```text
failed_from path
failed_from run_id
failed_from SHA-256
selected IDs
```

Selectors may be combined. `--failed-from` first establishes the FAIL subset; `--test`, `--match`, or `--selection` then narrows it.

## Load / capacity boundary

The scheduler uses two independent limits:

1. `max_parallel`: hard ceiling owned by this orchestrator.
2. `CapacityProvider.available_slots()`: polled external concurrency allowance for this orchestrator **right now**.

The effective concurrency limit is:

```text
min(max_parallel, available_slots())
```

If the external value drops below the number already running, current jobs are not killed; the scheduler simply submits no new work until capacity allows it.

Polling interval is configurable:

```yaml
scheduler:
  capacity_provider: command
  max_parallel: 8
  poll_interval_s: 5.0
  config:
    command: ["my-farm-capacity", "--queue", "verification"]
    timeout_s: 10
```

The command contract is deliberately tiny: print one non-negative integer to stdout. The wrapper command may inspect LSF, Slurm, a proprietary farm, host load, or anything else; core does not care.

A fixed provider is also included for local tests:

```yaml
scheduler:
  capacity_provider: fixed
  max_parallel: 2
  poll_interval_s: 0.2
  config:
    slots: 2
```

## Canonical result

Adapters translate project-specific observations into a stable result model:

```json
{
  "schema_version": 1,
  "run_id": "...",
  "name": "my-regression",
  "started_at": "...",
  "finished_at": "...",
  "duration_s": 123.4,
  "status": "FAIL",
  "summary": {
    "total": 3,
    "pass": 2,
    "fail": 1,
    "error": 0,
    "skip": 0
  },
  "tests": [
    {
      "id": "failing_test",
      "status": "FAIL",
      "duration_s": 0.01,
      "reason": "exit=7",
      "metadata": {}
    }
  ]
}
```

Canonical testcase statuses are `PASS`, `FAIL`, `ERROR`, and `SKIP`. Core validates that the adapter returns exactly one result for every executed job.

A future history/UI layer should consume `result.json`; it should never parse simulator, board, or project-specific logs directly.

## Extension contracts

### ExecutionAdapter

```python
setup(context)
plan(context) -> list[Job]
execute(context, job) -> JobExecution
collect(context, executions) -> list[TestResult]
```

### SourceProvider

```python
materialize(source, destination) -> resolved_evidence
```

### CapacityProvider

```python
available_slots() -> int
```

These three boundaries are the architecture. Keep project-, source-control-, and farm-specific knowledge outside core.

Built-in plugins may use short names. Project-owned plugins may live in another installed Python package and use `module:Class`:

```yaml
execution:
  adapter: my_soc_verification.regression:Adapter
```

See `Documentation/Integration_Guide.md` and `examples/external_adapter/`.

## Demos

### Zero-integration Linux sanity

```bash
reg all examples/sanity-linux.yaml
```

This runs `pwd`, `ls`, `mkdir`, and `rm` as fake tests behind the demo adapter. Core never interprets those commands.

### Self-hosted demo

```bash
reg all examples/self-host.yaml
```

Here regorch schedules selected groups of its own pytest suite through the concrete `selftest` adapter. This proves the orchestrator can orchestrate itself without adding pytest semantics to core.

### External project adapter

```bash
pip install -e examples/external_adapter
reg all examples/external-adapter.yaml
```

The example adapter is outside the `regorch` package and is loaded through `module:Class`, demonstrating the intended project integration model.

### Explicit FAIL rerun

```bash
reg all examples/regression-fail-demo.yaml || true
reg run examples/regression-fail-demo.yaml --failed-from <chosen-run-dir>
```

Use the actual generated run directory rather than an implicit "latest" selector.

## Documentation

Start with:

- `Documentation/Getting_Started.md`
- `Documentation/Architecture.md`
- `Documentation/Architecture_Contract.md`
- `Documentation/Integration_Guide.md`
- `Documentation/Demos.md`
- `Documentation/ADR/`
