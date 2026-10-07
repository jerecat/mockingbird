---
name: verify-python-compatibility
description: Verify Mockingbird's shared Python workaround when changing runtime code, tests, examples, dependencies, or test tooling, and before claiming compatibility or release readiness. This is a Mockingbird project requirement, not a general Python policy.
---

# Verify Python compatibility

Treat compatibility as a completion condition for each relevant change. A prior
commit's successful run does not verify the current revision.

## Required environments

- Run the full suite in the normal supported development environment.
- Run the workaround suite with Python 3.10.19, PyYAML 5.4.1 and pytest 9.0.3.
  Read the shared-Python workaround in `README.md` before testing. Preserve the
  distinction between this source-checkout workaround and package metadata
  requiring Python >=3.11 and PyYAML >=6.0,<7.
- Do not install or upgrade packages in a user's shared computing-centre Python.
  Use an isolated verification environment when dependencies need preparation.

From the repository root, select the intended interpreter explicitly:

```sh
COMPAT_PYTHON=/path/to/python3.10
"$COMPAT_PYTHON" -c 'import sys, yaml, pytest; print(sys.version); print("PyYAML", yaml.__version__, "pytest", pytest.__version__)'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$COMPAT_PYTHON" -m pytest -q --ignore=tests/test_cli_aliases.py
```

The sole existing exclusion covers two CLI registration tests importing
Python 3.11's `tomllib`. Do not silently add exclusions or skip new regression
tests to obtain a passing result. Investigate failures; document and explain any
necessary change to the workaround. Do not claim support below Python 3.10.

When changing lifecycle responsibilities, the focused tests, or mutation tooling,
also run in both environments:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$COMPAT_PYTHON" tools/check_lifecycle_mutations.py
```

Use the normal environment's interpreter for its corresponding run. Consult
`Documentation/Lifecycle_Testing.md` for the mutation check's scope and limits.

## Completion report

Report actual interpreter/dependency versions, commands, pass/fail results,
exclusions and unverified environments. Never substitute a Python 3.12 result
for a Python 3.10 result. If the compatibility environment cannot be run, state
that verification is incomplete rather than claiming compatibility.

Update README workaround commands when they change. Keep environment-specific
exceptions visible there. For documentation-only changes, check the instructions
against recorded evidence; rerun commands if their behaviour or accuracy changed.
