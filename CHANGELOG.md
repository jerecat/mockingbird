# Changelog

## 0.3.0

- Added executable architecture-contract tests.
- Added `Documentation/` with architecture, architecture contract, getting started, integration guide, demos, and ADRs.
- Added external `module:Class` loading for execution, source, and capacity plugins.
- Added zero-integration Linux sanity regression.
- Added self-hosted demo where regorch orchestrates selected groups of its own pytest suite.
- Added a project-owned external adapter package example.
- Kept concrete execution, SCM, and load semantics outside core.

## 0.2.0

- Added mixed Git/SVN source materialization.
- Added Context -> Plan -> Run -> Result evidence chain.
- Added explicit `--failed-from` selection provenance.
- Added editable selection files and ID-based selection.
- Added generic capacity polling and max-parallel scheduling.
