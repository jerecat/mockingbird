# Testing lifecycle responsibilities

A passing test suite does not establish that every operation is necessary. Start
with a user requirement: who consumes this output, which phase owns it, and what
must remain unchanged? Then encode observable consequences in pytest.

## Techniques used here

| Requirement | Test technique | Coverage |
| --- | --- | --- |
| Standard commands need no adapter workspace | Absence assertions plus real setup/run | `test_command_workspace.py` |
| Existing user files survive preparation | Preservation assertion | `test_command_workspace.py` |
| Custom adapters retain their workspace contract | Compatibility case | `test_command_workspace.py` |
| Planning does not execute commands or repeat setup | Forbidden boundary calls; repeated planning | `test_lifecycle_effects.py` |
| Omitted setup and an empty job list require no setup work | Parametrized equivalent inputs | `test_lifecycle_effects.py` |
| Live YAML edits do not change a confirmed run | Forbidden plan/setup calls and observed original Job IDs | `test_lifecycle_effects.py` |
| Status only observes saved evidence | Process/collector prohibition plus filesystem comparison before and after collection | `test_lifecycle_effects.py` |
| Final collection does not repeat execution or collection | Repeated operation, preserved evidence and collection checkpoints | `test_lifecycle_effects.py` |

The filesystem comparisons cover the test's temporary user workspace, including
file contents and directory names. They do not measure reads, timestamp-only
changes, or transient writes later undone. Final collection may update derived
summaries and progress metadata, so its test preserves execution evidence and
final checkpoints rather than freezing every metadata file.

Boundary guards use pytest's `monkeypatch.context()` to limit their scope. Real
commands still execute when constructing run evidence; we do not replace the
whole lifecycle with mocks. A forbidden call raises a pytest failure so a product
error handler cannot silently convert it into an ordinary collection error.

## Run the checks

Use the Python environment that already runs the project tests:

```sh
python -m pytest -q tests/test_command_workspace.py tests/test_lifecycle_effects.py
python tools/check_lifecycle_mutations.py
python -m pytest -q
```

The mutation check first runs the focused suite unchanged, then introduces four
known regressions, one at a time, into a temporary copy:

1. Prepare creates the unused command workspace.
2. The standard adapter setup hook creates it again.
3. Planning invokes setup.
4. Collection invokes the collector again for a final result.

Each mutation must fail its designated test with an assertion or the explicit
forbidden-operation failure. Collection errors, syntax errors, non-test failures,
and a failing baseline are not successful detections. The script exits nonzero
if a mutation survives or a source anchor changes. It copies only source, tests,
and pytest configuration into a small temporary directory and removes that copy
on exit. It does not edit the checkout, clone repositories, or require new pip
packages. Pytest temporary files follow its normal retention policy.

This is targeted mutation testing, not a project-wide mutation score or a run of
mutmut. It proves sensitivity to these four faults only. For a broader campaign,
mutmut can generate mutations; surviving mutants still need human interpretation.

## When adding behavior

Write down the allowed output and prohibited side effects before writing the
assertions. Cover the valid transition and an invalid or repeated transition.
Prefer user-visible files/results over private call counts. Where optional inputs
should be equivalent, check both variants. Temporarily break the relevant behavior
to verify that the test detects it; keep a reproducible mutation for significant
regressions. Avoid adding abstractions solely to make tests easier.

Generated state-machine tests (for example Hypothesis rule-based state machines)
are a possible next step when action sequences outgrow explicit cases. They are
not a dependency here. Neither mutation testing nor stateful testing can decide
whether a feature should exist: the requirement and its consumer remain review
inputs.

## References

- [pytest monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html): scoped replacement and prohibiting unwanted operations.
- [mutmut](https://mutmut.readthedocs.io/en/latest/): mutation testing to assess test sensitivity.
- [Hypothesis stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html): action sequences and invariants against a model.

Named-plan journeys in `test_plan_refresh.py` cover confirmation replacement and
failure, removed/renamed YAML, history and saved-plan inspection, concurrent
execution/replanning, latest-started selection, automatic paths, migration errors
and legacy run inspection/collection. Preparation readiness is separate from
live YAML edits.

## Verified named-plan implementation (2026-10-08)

| Environment | Versions | Suite | Mutations |
| --- | --- | --- | --- |
| Normal | Python 3.12.14 / PyYAML 6.0.3 / pytest 9.1.1 | 309 passed | All four detected |
| Shared-Python workaround | Python 3.10.19 / PyYAML 5.4.1 / pytest 9.0.3 | 307 passed | All four detected |

Commands, with the appropriate isolated interpreter selected:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$NORMAL_PYTHON" -m pytest -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$COMPAT_PYTHON" -m pytest -q --ignore=tests/test_cli_aliases.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$NORMAL_PYTHON" tools/check_lifecycle_mutations.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$COMPAT_PYTHON" tools/check_lifecycle_mutations.py
```

The Python 3.10 exclusion is unchanged: two CLI registration tests import
Python 3.11's tomllib. No new exclusions or dependency changes were needed.

An additional 32-command CLI rehearsal used a fresh directory and an existing
project worktree, following the shell-to-MB guide. It checked missing preparation
and plan guidance, optional setup, literal argv and saved cwd, execution and
collection, unconfirmed YAML edits, confirmation from another YAML, YAML deletion,
three retained runs, history and historical plan inspection, explicit old-run
collection without changing the latest run, invalid selections/run IDs, and
setup failure -> script edit -> retry -> plan -> run -> collect. The project
result paths and saved plan inputs matched the guide's predictions.

Both suites also execute the basic/advanced guided tutorials, mixed verdicts,
pending/collection-error retries, real SIGINT recovery, JSON output, capacity
gating, legacy records, replan during execution, and out-of-order run completion.
Interactive confirmation freezes the displayed plan and selection before the
callback; cancelling creates no run. Selection-export errors after successful
confirmation report that the plan was already confirmed.

Representative output from the rehearsal (run IDs abbreviated here):

```text
Confirmed: worktree-demo (1 jobs)
  - test_basic
Next: mb run worktree-demo

Collection: 1/1 complete
Result: PASS
  PASS 1  FAIL 0  ERROR 0  SKIP 0
  pending 0  uncollected 0  collection error 0

Plan: worktree-demo
RUN          EXECUTION  RESULT       JOBS
<third-run>  EXECUTED   PASS         1
<second-run> EXECUTED   UNCOLLECTED  1
<first-run>  EXECUTED   PASS         1
```

Validation uses local scripts, mock simulation output and local repositories.
It does not establish real VCS/board/farm behaviour or byte-for-byte reproduction
of mutable external inputs. See Named_Plans.md for ownership and locking limits.
