# Plan registration and directory-changing operation review

Verified on 2026-10-08 for the implementation in ADR 0015.

## Scope

The operator is one user with unique plan names. Changing terminal cwd must not
select a different plan or create another history. Quality-history consumers
may read results produced by multiple operators; that does not change plan
ownership or the existing per-run result contract.

First prepare registers the absolute project directory. Named operations resolve
that registration. Existing prepared plans can be registered by confirming YAML
from the original project directory. Storage stays in work/<plan>/, and each run
retains its own plan.json. Collect continues to replace that run's result.json.

## Verification environments

| Environment | Versions | Full suite | Lifecycle mutations |
| --- | --- | --- | --- |
| Normal | Python 3.12.14, PyYAML 6.0.3, pytest 9.1.1 | 323 passed | All four detected |
| Shared-Python workaround | Python 3.10.19, PyYAML 5.4.1, pytest 9.0.3 | 321 passed | All four detected |

Commands, with each variable pointing to its isolated interpreter:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$NORMAL_PYTHON" -m pytest -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$COMPAT_PYTHON" -m pytest -q --ignore=tests/test_cli_aliases.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$NORMAL_PYTHON" tools/check_lifecycle_mutations.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$COMPAT_PYTHON" tools/check_lifecycle_mutations.py
```

The compatibility exclusion is unchanged: two tests import Python 3.11's
tomllib. No other tests were excluded. Runtime source-checkout compatibility is
distinct from the package metadata requiring Python >=3.11 and PyYAML >=6.0,<7.

## Observed operation cycle

A separate 19-command public-CLI rehearsal used a project path containing spaces,
an unrelated caller directory, the plan's own storage directory, and a run
directory. Commands were invoked through python -m mockingbird.cli, the same
entry point registered for mb.

- An unknown name produced an error without creating local work directories.
- Prepare ran in the project; confirmation, preview and execution ran elsewhere.
- Status before collection found the same run from the unrelated directory.
- First collection produced one PASS and one PENDING; after the sample's external
  completion marker appeared, collection from the plan directory produced two PASS.
- Editing a differently named YAML elsewhere and confirming the same plan added
  a Job for a second run, while preserving the first run's plan and result.
- Collecting the first run again did not change the latest-started pointer.
- History elsewhere showed the new uncollected run above the previous PASS run.
- Malformed YAML failed confirmation and preserved the latest saved plan.
- After deleting both input YAMLs, status from inside the second run directory
  still found that run. Historical plan inspection remained available.

Additional regression journeys cover prepare/all from a different cwd; saved
setup, capacity and collector cwd; acquisition of a newly added relative local
Git source; explicit external/legacy runs without registration; migration without
repeating preparation; missing locations; duplicate legacy environments; failed
prepare retry; concurrent name reservation; and repeated isolated tutorials.

The broader existing suite also covers setup failure/retry, interrupted run and
collection, mixed verdicts, collector failures, source preservation, atomic
confirmation and frozen run contracts.

## Limits and contracts

Run/result schemas and collector outputs are unchanged. An unknown plan now
returns an error instead of a misleading empty history. Named lookup requires
one-time registration of older prepared plans. Explicit --run-dir stays available
without registration and does not change the user's name mapping.

The registry does not relocate prepared trees or rewrite absolute artifact paths.
Missing locations must be restored, or explicitly forgotten and prepared anew.
CLI file arguments remain caller-relative. Source providers receive the saved
project directory as the runtime-only _invocation_dir field; built-in providers
use it for relative source acquisition/probing. Guided tutorials select an
exercise-local registry and print its environment setting for manual continuation.

History remains one row per run, ordered by execution started_at. Collecting an
already-final run still regenerates result generated_at, so collection time must
not be used as the execution timeline. Cross-operator result aggregation is a
consumer of saved result files, not a new shared-plan feature in this change.
