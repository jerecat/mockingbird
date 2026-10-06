# ADR 0003: Separate human intent from machine evidence

Status: Accepted

## Context

A mutable user configuration and an immutable record of what actually happened have different purposes.

## Decision

Use YAML for human-authored regression intent and generated JSON for resolved/frozen evidence.

```text
regression.yaml  -> intent
context.json     -> resolved context
plan.json        -> discovered plan
run.json         -> execution evidence
result.json      -> normalized result evidence
```

## Consequences

Branch names and defaults may be convenient in YAML while resolved commit/revision data is retained separately for reproduction and history.
