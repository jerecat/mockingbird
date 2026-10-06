# ADR 0004: FAIL reruns require an explicit source result

Status: Accepted

## Context

"Rerun failed tests" is ambiguous when multiple historical runs exist. An implicit latest-run rule can execute the wrong subset and obscures provenance.

## Decision

FAIL-only selection requires `--failed-from <run-dir|result.json>`.

The new run records provenance for the source result, including its identity/hash and the selected IDs.

## Consequences

The command is slightly more explicit, but reproducibility and auditability are deterministic. Convenience aliases such as an implicit "last failed" are intentionally excluded from core behavior.
