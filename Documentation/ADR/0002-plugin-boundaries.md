# ADR 0002: Concrete behavior lives behind three plugin boundaries

Status: Accepted

## Context

The orchestrator must remain usable across simulators, boards, Git/SVN mixtures, and different compute farms.

## Decision

Concrete behavior crosses only:

```text
ExecutionAdapter
SourceProvider
CapacityProvider
```

Bundled short names are convenience implementations. Project-owned plugins may be installed externally and referenced as `module:Class`.

## Consequences

Core can evolve around lifecycle and evidence without absorbing VCS, board, SCM, or farm semantics. Project integration does not require a fork of core.
