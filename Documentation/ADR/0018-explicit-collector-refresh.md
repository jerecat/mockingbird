# ADR 0018: Explicit collector repair against existing execution evidence

Status: Accepted

## Context

A collector may need debugging or artifact-reporting fixes after expensive
execution has finished. Re-running simulation just to adopt a collector change
is unnecessary. Silently adopting the current plan would mix new execution
intent with old execution evidence.

## Decision

Add `collect --refresh` as an exceptional repair operation for command-adapter
runs. Validate the latest confirmed plan against the original saved plan; allow
only resolved collector settings to differ. Reject non-collector changes with
paths and old/new values before updating collection evidence.

Accept a refresh through one atomic run-level collection journal publication
containing both the new settings and reset verdict states. That journal becomes
authoritative for this run, including subsequent ordinary collection and status.
Keep original execution records immutable. Record adopted settings in result.json
and use them when exporting with save. Do not snapshot external script contents.

## Consequences

Final verdicts can be replaced explicitly without re-execution. Pending/error
retries continue the accepted settings and do not depend on a later plan.
There is no history of replaced verdicts; users retain copies when needed.
Unstarted Jobs cannot acquire execution evidence through refresh. Unsupported
adapters and legacy layouts fail clearly. Ordinary collection remains unchanged
for runs that have never accepted a refresh.

See [Collector repair](../Collector_Refresh.md) for failure and recovery semantics.
