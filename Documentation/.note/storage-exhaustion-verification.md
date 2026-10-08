# Verification review: storage exhaustion

## Scope and method

Apply `.skills/design-verification/SKILL.md` to persistence, dispatch, and recovery.
Existing maintenance tests cover several generic snapshot write failures, but
did not explicitly exercise ENOSPC or failed terminal-state publication.

Inject `OSError(errno.ENOSPC, ...)` at selected persistence boundaries in isolated
pytest directories. Do not fill a real disk. These tests verify application
responses to injected failures, not kernel/filesystem exhaustion, quota behavior,
or power-loss durability. No runtime behavior is changed by this review.

## Claims and evidence

| Claim or question | Stimulus | Oracle and observed evidence | Disposition |
| --- | --- | --- | --- |
| A failed JSON update preserves the prior complete snapshot | ENOSPC at fsync and replace | Prior bytes unchanged; temporary file removed | Verified, two cases |
| Failure to persist a returned execution stops subsequent dispatch | ENOSPC at execution.json | Only Job a executes; run records ERROR if its own storage is writable | Verified |
| Missing execution evidence cannot be fabricated during recovery | Restore storage after checkpoint failure | collect reports two uncollected Jobs; no complete result | Verified limitation |
| Completed Job checkpoints suffice if the terminal run record cannot be saved | ENOSPC at final run.json | Two checkpoints survive, but run remains RUNNING and collect rejects it after storage is restored | Known recovery gap; characterization only |
| Retrying a failed result publication does not rerun final collectors | ENOSPC at result.json, then restore storage | Saved per-Job collection checkpoints reused; two collector calls total; final result PASS | Verified |

The stale RUNNING case is **not** a desirable recovery requirement. Its regression
test characterizes the current limit and should change when an explicit recovery
policy is implemented. Automatically treating RUNNING as finished is unsafe:
the same status can also describe a live run.

## Operational consequences

Free space before retrying and inspect execution evidence. A Job command may have
performed side effects even when its execution checkpoint is missing; another run
must not be assumed to be a safe resume. Run starts a new run.

A failure while publishing the terminal run record can leave the run uncollectable
even after storage is restored. There is no verified automatic repair path in
this review. Preserve the run evidence and decide whether project-side rerunning
is safe. Do not blindly edit records or delete prior runs.

Child stdout/stderr are direct file descriptors, so write failures are observed
by the child, not by an MB logging reader. Whether the child fails, suppresses
errors, or continues is project-specific. no-check does not validate log
completeness or successful execution.

## Verification execution

- Python 3.12.14 / PyYAML 6.0.3 / pytest 9.1.1: full suite **328 passed**.
- Python 3.10.19 / PyYAML 5.4.1 / pytest 9.0.3: workaround suite **326 passed**,
  with the existing `tests/test_cli_aliases.py` exclusion for tomllib.
- All four lifecycle mutation seeds detected in both environments.
- Added `tests/test_disk_full.py`: five bounded fault-injection cases.

Run:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /path/to/python3.10 -m pytest -q --ignore=tests/test_cli_aliases.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/check_lifecycle_mutations.py
```

## Remaining evidence

Real exhausted filesystems, quota/inode exhaustion, failure during child log
writes, failure while opening log files, cleanup failures, and combined failures
across multiple checkpoint writes are not verified here. Capacity and permission
preflight checks cannot guarantee later writes. Treat the tests as bounded
evidence for the claims above, not a general fault-tolerance certification.
