# ADR 0008: Resolved Jobs and repeatable collection

Status: accepted, 2026-10-07

## Context

A common command/collector for an entire execution set cannot express ordinary
heterogeneous Jobs. Requiring 500 repeated contracts is equally undesirable.
Executor return codes are execution facts, not automatically test judgements.
External results may not be available in the first collection cycle.

## Decision

- Users may write complete per-Job contracts; defaults are optional shorthand.
- Plan applies defaults, overwrites explicit Job fields, validates, and freezes
  the full contract. No runtime default resolution occurs.
- Dispatch follows list order under the existing capacity gate. No dependency
  graph, before/after phases, or project-specific Job categories are introduced.
- Absent collection policy resolves to no-check. This collector returns PASS/[]
  without interpreting evidence. Remove generic exit-code collection.
- Persist execution evidence as each command returns, independently of collection.
- Link contract, execution, and result by Job ID within a run; use run ID as the
  outer identity. External commands receive MB_JOB_ID and MB_RUN_ID by contract.
- Repeated collect on that run visits only unresolved Jobs. PENDING and collection
  ERROR are not TestResult. Valid final PASS/FAIL/ERROR/SKIP results are immutable.
- Checkpoint each collection attempt; preserve atomic files and exclude concurrent
  collect on one run. No daemon, automatic polling, or automatic execution retry.
- Keep artifacts opaque list[str].

This supersedes ADR 0007's exit-code mode, common-only execution fields, and
mandatory explicit collector. It refines AC-16/17/18 without changing the core's
execution-detail-blind boundary or capacity gate.

## Consequences

Evidence schema version 2 distinguishes collection state from final judgement.
Older runs require their original software version; old plans must be rebuilt.
A collector must tolerate being called again after a pending/error outcome or an
interruption before its checkpoint. An unresolved run is never reported as PASS.
