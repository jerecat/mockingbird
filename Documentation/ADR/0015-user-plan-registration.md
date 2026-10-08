# ADR 0015: Resolve plan names independently of the caller's directory

Status: accepted, 2026-10-08. YAML confirmation and registration recovery amended by ADR 0016.

## Context

The operator is one user. They work with plans and runs, and expect `mb status
smoke` to mean the same plan after changing directory. ADR 0014 instead scoped
names to the invocation directory. This made a completed plan appear unprepared
or unrun elsewhere and let recovery create another environment with the same
name. The earlier 32-command rehearsal held cwd fixed and missed this gap.

Results from multiple operators may later contribute to a DUT quality timeline.
That concerns reading run evidence; it does not require shared plan management,
user accounts or a new result format. Plan changes are already preserved in each
run's plan.json, and collect updates that run's result.json.

## Decision

- Names are unique within one user's registry, independent of caller cwd.
- First prepare reserves a name and records its absolute project directory.
  Storage remains at that project's work/<plan>/; execution cwd stays there.
- Registrations are small JSON files under ~/.local/state/mockingbird/plans/.
  An absolute MB_STATE_DIR override supports isolated environments and tests.
- Same-name prepare/plan/all uses the registered project. Named setup, dry-run,
  run, status and collect resolve it without opening the original YAML.
- Explicit confirmation from the original directory registers a legacy prepared
  plan without repeating preparation. Conflicting legacy locations are reported.
- Unknown names and missing locations produce actionable errors. No parent
  search, nearest-plan selection, implicit relocation or history merging occurs.
- Registration is reserved before prepare side effects, with a per-name lock
  and atomic JSON replacement. A failed prepare can be retried at its recorded
  location. Operators may explicitly remove an unused registration; it does not
  delete source trees or results.
- Default status/collect still chooses the latest-started run, including when
  it has no final results. Recollecting an older run does not change the pointer.
- Explicit --run-dir can read compatible external or legacy evidence without
  requiring or changing registration. It retains the saved plan-name check.
- Run/plan/result schemas and collector contracts remain unchanged. Histories
  use execution started_at, not result generated_at, which changes on collect.
- Guided tutorials use their own registry within the exercise directory and
  print the environment setting needed for manual continuation and cleanup.

## Consequences

A single lookup file replaces an implicit cwd-dependent identity. A second
project needs another plan name. YAML and CLI file arguments still resolve from
the caller, while project commands use the saved execution cwd. Moving prepared
trees is not an automatic relocation operation; saved artifact paths remain
absolute. Registry lifecycle is explicit and does not add a daemon or database.

Regression coverage changes cwd across confirmation, execution, collection,
latest/historical inspection and reprepare, and exercises migration, stale
locations, duplicate legacy environments and independent tutorial sessions.
See the [verification record](../.note/plan-registry-review.md) for versions,
commands, observed output and remaining limits.
