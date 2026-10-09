# CLI visual grouping review

## Cause and decision

The UX rules covered concise summaries, aligned tables, progress, recovery, and
machine output. They did not specify boundaries between those information units.
Individual messages were useful, but their composed transcript was too dense.

Use explicit blank lines at meaning changes and indentation for supporting
information. Keep related rows together. Implement this in presentation code,
without stream interception or a new formatting framework. See
[CLI experience](../CLI_Experience.md#visual-grouping) for the reusable policy.

## Verification contract and evidence

| Requirement | Scenario / oracle | Evidence |
| --- | --- | --- |
| Job and summary boundaries are visible | Two-Job run, completion/evidence adjacent, next action separated | CLI journey assertions and inspected transcript |
| Composed phases remain readable | `all` with setup and two Jobs | Executed; exit 0 and PASS 2; transcript inspected |
| Tables remain compact and aligned | status before/after collection, history, doctor details | Advanced tutorial and separate history/doctor transcript |
| Recovery remains actionable | Missing registration/prerequisite, invalid definitions, selection and run paths | CLI suite; printed recovery commands exercised; multiline error indented |
| Tutorial explains nonzero outcomes | Advanced tour through pending, malformed output and repaired collectors | Executed; expected intermediate exits, final tutorial exit 0 |
| Machine interfaces are preserved | Parse JSON; compare exits and saved evidence through existing journeys | Full suite in both environments; adapters/lifecycle unchanged |
| Cancellation preserves evidence | SIGINT and collection-interruption tests | Existing suite in both environments |
| Save and setup follow-up is distinct | `all` setup and `save --as` | Executed; output inspected |

Normal environment: Python 3.12.14, PyYAML 6.0.3, pytest 9.1.1;
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`: 361 passed.

Shared-Python workaround: Python 3.10.19, PyYAML 5.4.1, pytest 9.0.3;
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --ignore=tests/test_cli_aliases.py`:
359 passed. The documented two tomllib-dependent registration tests are the only
exclusion. Dependencies were installed only in isolated temporary environments.
PyYAML 5.4.1 required a Cython <3 build environment; product dependencies did not
change. Final doctor/save presentation adjustments were checked with the focused
CLI, doctor, doctor-display and save suites in both environments.

Limits: this is a transcript review, not a measured usability study. No new
remote git/repo acquisition rehearsal was performed for this presentation-only
change. Child output and saved logs are intentionally not reformatted, including
output without a trailing newline. Very long identifiers/paths can still wrap.
