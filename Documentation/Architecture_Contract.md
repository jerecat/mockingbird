# Architecture Contract

These rules are treated as executable compatibility constraints.

## AC-1: Core is execution-detail blind

Core may orchestrate lifecycle, selection, evidence, directory allocation, and
scheduling. It must not import concrete adapter/source/capacity implementations
or execute project commands directly.

## AC-2: Project execution crosses only ExecutionAdapter

```text
probe(context)
setup(context)
plan(context)
execute(context, job, execution_context)
collect(context, executions)
```

Only adapters interpret project commands, simulator output, board responses, or
verification result rules.

## AC-3: Job identity defines rerun granularity

A Job is an independently schedulable and independently rerunnable unit.

Required:

- unique within a plan;
- non-empty stable string identity;
- no leading/trailing whitespace;
- no control characters;
- JSON-serializable payload and metadata.

`--failed-from` selects failed **Job IDs**. Core does not split a Job into finer
project-defined tests.

## AC-4: Core allocates per-job ExecutionContext

Core creates isolated `work`, `artifacts`, and `logs` directories for every
selected Job and passes them to `execute`. Directory names are derived safely and
must not directly trust Job IDs as paths.

## AC-5: Large process output is file evidence

Adapter implementations must not place unbounded stdout/stderr bodies into
canonical JSON. File references and small metadata are the expected evidence.

The bundled process utility streams stdout/stderr directly to files and has no
`shell=True` API.

## AC-6: Process timeout is group-scoped

For subprocess-based adapters, the recommended utility starts a new process
session. Timeout termination targets the process group with SIGTERM followed by
SIGKILL after a grace period.

## AC-7: SCM semantics cross only SourceProvider

Core requests materialization but does not know Git/SVN commands. Built-in Git
and SVN are plugins, not core concepts.

## AC-8: Load semantics cross only CapacityProvider

Core knows only `available_slots()` and `max_parallel`. Queue/farm semantics
remain outside core.

## AC-9: Intent and machine evidence are separate

```text
regression.yaml   human intent
context.json      resolved/frozen context
plan.json         discovered canonical plan
run.json          selected/executed run evidence
result.json       canonical result evidence
```

## AC-10: FAIL rerun has explicit provenance

A FAIL-only rerun names the previous run/result explicitly. The new run records
the source result path, run ID, SHA-256, and selected Job IDs.

## AC-11: Integration must not require core modification

External `module:Class` plugins are supported for execution/source/capacity.
Project integration belongs in a project-owned package.

## AC-12: Connection checks are first-class

Every extension contract offers `probe`. `reg doctor` orchestrates these probes
without materializing sources or running regression Jobs. Missing custom probe
logic may produce WARN; concrete connection failure produces FAIL.

## AC-13: Conformance is reusable

`regorch.testing` provides execution/source/capacity conformance helpers that can
be used from project-owned pytest suites. Contract changes require corresponding
conformance and documentation updates.

## Change rule

If a feature violates one of these rules, either redesign it or add an ADR that
explicitly replaces the rule and update architecture tests in the same commit.
Do not weaken a contract test merely to make a feature pass.
