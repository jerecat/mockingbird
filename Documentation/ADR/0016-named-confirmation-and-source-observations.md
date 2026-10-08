# ADR 0016: Named confirmation and run-start source observations

Status: accepted, 2026-10-09

## Decision

After `prepare YAML`, use the same plan name for setup, plan, dry-run, run,
collect and status. This lets operators recall a command and change only its verb.
`plan PLAN` rereads the absolute YAML path saved by the latest successful prepare;
it rejects missing files or changed plan names and preserves the previous confirmation.
There is no name/path guessing. Doctor and all retain YAML entry points.

A successful prepare updates the registered YAML path and preparation evidence.
Recovering a deleted registration requires prepare from the original directory,
then optional setup and plan. Existing source trees and historical runs are retained.
This supersedes ADR 0015's YAML-based confirmation/legacy registration shortcut.

Optional source-provider `observe(source)` supplies read-only run-start evidence.
Git supplies prepared_commit, current_commit and dirty. Core records observations
in each run.json; CLI displays them. Providers without observation support still work.
Observation failures record unknown/error rather than stop execution. Git queries
are local and bounded, do not acquire sources, and occur once before dispatch.

Dirty includes staged, unstaged and untracked changes, excluding ignored files.
HEAD equality does not imply identical working-tree contents. Reprepare refreshes
the comparison baseline, not historical records. No diff or source snapshot is saved.
The additional run.json field is additive; execution/collection states are unchanged.

## Verification

Cover subdirectory YAML, different caller cwd, optional setup, YAML edits/moves,
missing/mismatched YAML, preservation of confirmed plans and historical runs,
clean/dirty/staged/untracked/ignored Git state, committed HEAD changes, baseline
refresh and missing-source observation failure. Run both supported verification
environments and the existing lifecycle mutation checks.

Verified for this change:

- Python 3.12.14 / PyYAML 6.0.3 / pytest 9.1.1: 330 tests passed.
- Python 3.10.19 / PyYAML 5.4.1 / pytest 9.0.3: 328 tests passed;
  only the existing tests/test_cli_aliases.py exclusion applies.
- `tools/check_lifecycle_mutations.py`: all four seeded regressions detected
  in both environments.
- `mb tutorial --yes` completed with named confirmation. Real local Git tests
  verified unchanged/dirty/changed HEAD, reprepare, unknown observations and
  immutable historical observations. No remote farm or simulator was used.
