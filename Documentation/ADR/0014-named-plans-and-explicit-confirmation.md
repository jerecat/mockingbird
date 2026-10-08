# ADR 0014: Named plans and explicit confirmation

Status: accepted, 2026-10-08

The invocation-directory identity and absence of a registry below are superseded
by [ADR 0015](0015-user-plan-registration.md). The remaining lifecycle and result
decisions continue to apply.

## Context

A user writes a plan, confirms it, runs it, checks results, and edits or starts
another plan as work progresses. Independent names, workspace/run-root settings,
YAML-path identity and live-YAML comparisons made this ordinary workflow harder
than necessary. Confirmation is already an explicit statement of intent.

## Decision

- Top-level `plan` names the continuing plan. Source `name` and Job `id` stay.
- MB derives `work/<plan>/` and its `runs/` directory from the invocation
  directory. No set/list/revision IDs or global plan registry are introduced.
- Prepare records the environment; setup executes its saved optional preparation
  commands. Plan confirms a complete execution context and resolved Jobs.
- The last successful confirmation supplies future runs. Failed confirmation
  preserves the prior plan. Confirmation has one atomic publication point.
- Run consumes the saved plan without rereading or comparing YAML. Setup, run,
  dry-run, status and collect accept a plan name.
- Each run saves its complete plan and explicit selection before dispatch.
  Replanning does not change existing runs or their later collection.
- History, results and saved plan details are accessible without the original
  YAML. The default run is latest-started, unaffected by later completion or
  collection of an older run.
- Preparation changes need explicit preparation. Locks prevent MB from modifying
  the prepared environment during active execution/planning/collection. Parallel
  runs and planning may share it; project outputs remain project-owned.
- Existing source/worktree preservation, serial Job dispatch, capacity gates,
  execution/result separation and collector/no-check semantics remain intact.

## Consequences

ADR 0013's run-time YAML comparison and interactive replanning are superseded.
The old plan-validation failure rule in ADR 0008 is superseded. Prepare/setup
failure invalidation from ADR 0010/0012 remains necessary because those phases
can modify actual files. Metadata alone does not preserve mutable external
inputs; wrappers own tool/source/environment pinning and output isolation.

See [Named plans](../Named_Plans.md) for operations, formats, concurrency limits
and migration. Verification covers the approved user journeys, both supported
verification environments, and targeted lifecycle mutations.
