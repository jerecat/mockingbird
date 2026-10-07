# ADR 0009: Serial execution as the current operating policy

Status: accepted, 2026-10-07

## Context

The current requirement is to execute Jobs one at a time in list order.
Parallel execution is not normally needed. Introducing it into normal operation
would require deciding how ordering and dependencies are represented, adding
complexity that is not justified by the present use case.

The existing scheduler already supports max_parallel. The existence of that
implementation must not be mistaken for a requirement to use or expand it.

## Decision

- Normal operation and current operational rehearsals use max_parallel: 1.
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

This is an operating-policy clarification of ADR 0008. It does not remove the
existing parallel scheduler, change user-owned definitions automatically, or
invalidate its capacity/concurrency unit tests. Bundled examples and integration
guidance use max_parallel: 1 to match the normal operating policy.
Any future proposal to use parallel execution should explicitly revisit this ADR
rather than inferring approval from existing code or examples.
