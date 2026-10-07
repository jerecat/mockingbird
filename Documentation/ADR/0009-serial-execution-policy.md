# ADR 0009: Serial execution as the current operating policy

Status: accepted, 2026-10-07

## Context

The current requirement is to execute Jobs one at a time in list order.
Parallel execution is not normally needed. Introducing it into normal operation
would require deciding how ordering and dependencies are represented, adding
complexity that is not justified by the present use case.

The original scheduler supported max_parallel. The existence of that
implementation must not be mistaken for a requirement to use or expand it.

## Decision

- Normal operation and current operational rehearsals use max_parallel: 1.
- Enforce this in configuration validation and at runtime: max_parallel must
  be the integer 1. Omission defaults to 1. Reject every other value, including
  booleans, floats and strings; do not silently coerce or clamp them.
- Runtime validation covers previously prepared contexts as well as direct
  scheduler calls, before any Job is dispatched. Pytest protects both boundaries.
- Start the next Job only after the previous local command has returned or its
  bounded local execution has ended, and the capacity gate permits dispatch.
- Do not introduce a dependency graph, before/after phases, or special Job types.
  Compile, sleep, simulation submission, and cleanup remain ordinary Jobs.
- Parallel execution is deferred as an operating requirement. Consider it again
  only when an explicit use case calls for it, together with the ordering and
  dependency semantics needed by that use case.
- Scale tests, including a 500-Job rehearsal, should first exercise serial
  execution and collection. Job count alone does not justify parallel dispatch.

## Execution versus external completion

For a submit-and-return command, serial execution waits for that local command
only. It does not wait for the external simulation or farm job to finish.
External work may therefore overlap even with max_parallel: 1. The project-owned
command contract is responsible for any required external synchronisation.

Collector cycles remain separate: they obtain final results or leave Jobs
unresolved. They do not become implicit dependency barriers between commands.

## Consequences and scope

The list and local command completion define current execution order. Capacity
remains a hard dispatch gate, including when it temporarily reports zero.

This extends ADR 0008 with an enforced serial-only policy. The existing scheduler
implementation now dispatches one Job and waits before considering the next.
One worker thread is retained so graceful SIGINT can drain the current Job and
save its evidence; Future sets, submission arithmetic and evidence locks are
unnecessary. User definitions and
previously prepared contexts requesting another value fail explicitly.
Tests verify rejection and serial capacity gating. Bundled examples and
integration guidance use max_parallel: 1.
Any future proposal to use parallel execution should explicitly revisit this ADR
rather than inferring approval from existing code or examples.
