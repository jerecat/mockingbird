# ADR 0001: Context -> Plan -> Run -> Result

Status: Accepted

## Context

Regression execution needs reproducibility and traceability without teaching core about project-specific execution details.

## Decision

The canonical lifecycle evidence is split into four concepts:

```text
Context -> Plan -> Run -> Result
```

`context.json` freezes resolved environment/source context. `plan.json` records discovered canonical jobs. `run.json` records a selected execution and scheduler policy. `result.json` records normalized results.

The frozen context is metadata, not a source-content snapshot. Sources may be
edited after preparation; recorded revisions describe the prepare-time baseline.
ADR 0011 defines non-destructive reuse of user-managed Git/SVN checkouts.

## Consequences

Each stage has a clear provenance boundary. Future UI/history code can consume canonical result/context evidence without parsing concrete simulator or board logs.
