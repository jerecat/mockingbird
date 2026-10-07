# ADR 0012: Declarative setup and explicit retry

Status: Accepted

## Context

Setup existed only as a Python adapter hook. The standard command adapter did
almost nothing, yet plan required users to invoke setup. Users could configure
run and collect but not preparation, creating an inconsistent external boundary.
Real preparation can fail, be edited in place, and be retried.

## Decision

Add an optional top-level setup command list using the same literal command,
args, timeout and defaults conventions as run, without a collector. Prepare
validates and freezes it. Execute synchronously in list order, require zero exits,
and stop on failure. Then call the existing execution adapter's setup hook.
Setup uses a dedicated process boundary and does not reinterpret run observations
or change run/collect judgement semantics.

Omitted/empty setup is optional for the built-in command adapter. Custom Python
adapters retain their hook requirement. Starting setup invalidates prior success
and the saved plan before any mutation. Success allows a new plan; failed,
interrupted or incomplete preparation blocks plan/run. Existing runs can still
be collected from their saved context.

Every attempt preserves its contract, records and command logs. Retry starts the
full list again, without rollback or deleting edits. Script/source edits are live;
YAML edits require another prepare. No automatic retry, resume, dependency graph,
capacity scheduling, or asynchronous setup collection is introduced.

## Consequences

Users can express preparation without writing Python adapters and inspect failed
attempts. Preparation wrappers must be repeatable and wait for their own work.
Setup exit status describes preparation success, not a regression test verdict.
Compile/cleanup remain ordinary run Jobs when users choose that lifecycle.
