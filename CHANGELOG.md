# Changelog

## Unreleased

- Show serial command progress and publish the latest run before dispatch.
- Show saved execution and collection states in `status`, including before first
  collection and after partial collection; add `status --json` for snapshots.
- Display collector reasons as timestamped observations, without external polling
  or changes to the collector contract. Saved RUNNING state is not a liveness check.

- Reuse existing Git/SVN checkouts without updating, cleaning, resetting or
  rejecting local edits. Record created/reused and the prepare-time local
  revision; changed source URLs/revisions apply only to new checkouts.

- Reject workspace/definition mismatches and block execution after partial prepare.
- Make per-Job execution and collection files authoritative; retain legacy
  schema-2 checkpoint compatibility and write aggregate views once per cycle.
- Share runtime/conformance validation and execution enrichment; reject invalid
  numeric boundaries before dispatch instead of coercing capacity values.
- Simplify serial scheduling while retaining graceful SIGINT drain behaviour.
- Terminate surviving process-group members even after parent exit, and clean up
  interrupted collector processes before propagating interruption.

- Enforce max_parallel as integer 1 in configuration and runtime, including old
  prepared contexts; reject parallel execution instead of silently clamping it.
- Align all bundled definitions and integration guidance with serial operation.
- Clarify final TestResult versus retryable CollectionAttempt throughout the guide.
- Record gracefully interrupted runs as INTERRUPTED and allow their saved
  executions to be collected; never-executed Jobs remain uncollected.
- Resolve defaults and per-Job overrides into complete validated plan contracts.
- Support per-Job command/collector, empty arguments, and implicit no-check.
- Remove generic exit-code judgement; preserve execution facts independently.
- Persist each execution immediately and checkpoint each collection attempt.
- Retry only unresolved collection states (PENDING or collection errors), with
  immutable final results, run/Job identity, and one-run collection locking.
- Add schema 2 evidence, separate incomplete summaries, and CLI exit 2 for pending.
- Keep list-ordered, capacity-gated dispatch without dependency semantics.


## 0.5.0

- Renamed the previous internal package/project name to `mockingbird`.
- Registered both `mockingbird` and `mb` console scripts to the same CLI entry point.
- Renamed the external adapter example package/imports to Mockingbird terminology.
- Updated documentation, examples, tests, diagnostics, and self-host naming to use Mockingbird consistently.
- Kept the internal `.reg/` metadata directory format unchanged to avoid coupling evidence layout to product branding.

## 0.4.0

- Added per-Job `ExecutionContext` with isolated work/artifact/log directories.
- Changed `ExecutionAdapter.execute` to receive the per-Job execution context.
- Added `mockingbird.adapter_utils.run_process` with file-streamed stdout/stderr,
  `shell=False`, `stdin=DEVNULL`, timeout handling, and process-group termination.
- Added `probe` hooks to ExecutionAdapter, SourceProvider, and CapacityProvider.
- Added non-destructive `mockingbird doctor` connection checks.
- Added reusable `mockingbird.testing` conformance helpers for project-side pytest.
- Defined Job as the independently schedulable/rerunnable unit and strengthened
  Job ID validation and documentation.
- Added adapter implementation/conformance documentation and ADRs 0005/0006.
- Added architecture tests for process I/O, timeout, doctor, conformance, and
  per-Job execution directories.

## 0.3.0

- Added executable architecture-contract tests.
- Added `Documentation/` with architecture, architecture contract, getting started, integration guide, demos, and ADRs.
- Added external `module:Class` loading for execution, source, and capacity plugins.
- Added zero-integration Linux sanity regression.
- Added self-hosted demo where mockingbird orchestrates selected groups of its own pytest suite.
- Added a project-owned external adapter package example.
- Kept concrete execution, SCM, and load semantics outside core.

## 0.2.0

- Added mixed Git/SVN source materialization.
- Added Context -> Plan -> Run -> Result evidence chain.
- Added explicit `--failed-from` selection provenance.
- Added editable selection files and ID-based selection.
- Added generic capacity polling and max-parallel scheduling.
