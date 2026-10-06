# Changelog

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
