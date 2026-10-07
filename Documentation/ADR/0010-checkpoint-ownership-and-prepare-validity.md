# ADR 0010: Checkpoint ownership and prepare validity

Status: accepted, 2026-10-07

## Context

Fault injection exposed three consistency failures: a different definition could
reuse a workspace silently; interrupted prepare could leave old evidence pointing
at partially updated sources; and collection ignored saved Job execution records
when updating their aggregate snapshot failed. Atomic file replacement alone does
not make multiple writes transactional.

## Decision

- A prepared workspace belongs to the canonical definition path in its context.
  Setup, plan and run reject another definition. Explicit prepare may replace that
  association. Edits to the same definition remain frozen until prepare succeeds.
  Collect checks the definition against the run's saved context, and does not
  require the current workspace to be prepared: an old run remains collectable
  after a later prepare fails.
- Before changing sources, prepare atomically creates `.reg/preparing.json`.
  It removes the marker only after both context and state are saved. While the
  marker exists, setup, plan and run fail closed. Recovery is another successful
  prepare, then setup and plan. Old source trees are not rolled back.
- For new runs, `jobs/<job>/execution.json` and `jobs/<job>/collection.json` are
  the authoritative, atomically replaced checkpoints. Collection attempts include
  run and Job identity. Checkpoints are saved before proceeding to the next Job.
- Run-level `executions.json`, `collection.json` and `result.json` are derived
  views. Execution writes its view once on exit; collection writes its views
  once after a sweep. A failed view write cannot invalidate saved Job evidence.
  New runs declare `checkpoint_storage: per-job` in `run.json`.
- Existing schema-2 runs without the marker retain their aggregate checkpoint
  format. They are read and collected under the old rules, not silently migrated.
- Runtime and the conformance kit share Job validation, execution enrichment,
  collection-outcome validation and capacity validation. Numeric timeouts and
  polling intervals must be finite positive numbers, excluding booleans. Capacity
  must be a non-negative integer, excluding booleans; no coercion or clamping.

## Consequences and limits

New checkpoint storage is linear in Job count rather than rewriting an entire
run for every Job. The two small per-Job files represent different concepts:
execution evidence and collection state, not duplicate copies of the same truth.

Run-level views can be absent or stale after interruption or a write failure.
Inspect per-Job records for live evidence. Repeating collect rebuilds collection
views and skips final checkpoints, without repeating execution.

This does not guarantee exactly-once external calls: a collector that completes
before its checkpoint write fails can be called again. Collectors must tolerate
retries. SIGKILL, power loss and overlapping prepare/setup/run against the same
workspace are not supported recovery/concurrency contracts. Per-run collect
locking remains supported. Serial execution is a per-run policy, not a global
lock across independent CLI processes.

Tests cover partial source updates, metadata write failures, aggregate write
failures, interrupted execution and collection, legacy checkpoint compatibility,
invalid numeric boundaries and conformance/runtime agreement.
