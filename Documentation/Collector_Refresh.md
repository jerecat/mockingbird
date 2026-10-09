# Repairing a collector without rerunning execution

Use this exceptional operation when debugging a collector or fixing its verdict
or artifact reporting. Normal collection continues to use saved contracts and
skips final results. This is not part of the normal run/collect workflow.

```sh
# Edit only collect settings in the registered YAML, then confirm them.
mb plan smoke
mb collect smoke --refresh
# Or explicitly target a historical run:
mb collect smoke --run <run-id> --refresh
```

Refresh re-collects all executed Jobs selected in that run, including final
PASS/FAIL/ERROR/SKIP results. It does not execute Jobs again. Jobs without execution
records remain uncollected. With no settings change, refresh still re-collects;
this supports editing the collector script at its existing path.

The latest confirmed plan is compared to the original run's saved plan. Only
resolved `collect` settings may differ. Changes to Job IDs/order, commands,
arguments, timeouts, metadata, scheduler, sources, setup or execution context
are rejected before collection records or results are modified. Shorthand and
default syntax are compared through resolved Jobs; generation timestamps,
configuration-file locations and orchestrator version metadata are ignored.
The command adapter and schema-3 per-Job run storage are required. Custom adapters
are rejected rather than guessing which part of their opaque contracts is a collector.

A rejection shows differing paths and Run/Plan values, followed by:

```text
--refresh accepts changes to collect settings only.
Non-collector settings also changed, so collection was not started.
Restore the other settings and run: mb plan smoke
Then retry: mb collect smoke --run <run-id> --refresh
Existing collection records and results were not changed.
```

If execution changes were intentional, create a new run instead. No automatic
prepare, checkout or execution is performed to resolve a mismatch.

## Records and recovery

Run-level `collection.json` atomically publishes the accepted `collectors` mapping,
`refreshed_at`, and reset Job collection states. For refreshed runs this file is
the authoritative checkpoint; old per-Job collection files are no longer read.
This keeps collector adoption and invalidation of previous verdicts inseparable.
Each new attempt updates that journal. Attempt counts restart for each refresh.

`run.json`, the run's `plan.json`, per-Job `execution.json`, and execution logs
remain unchanged. Collectors receive the original execution paths, IDs and cwd.
The collector subprocess can still have its own side effects, just as in ordinary
collection; it should not overwrite its input logs.

`result.json` is regenerated with `collection_config` containing the accepted
collector settings and refresh time. Final results are replaced, not archived.
Save a copy beforehand if you need previous verdicts for comparison. This records
settings, not a snapshot or hash of external collector script contents.

PENDING or collection errors resume using the accepted settings on the next
ordinary `mb collect`, even if the current plan has changed again. Interruption
also resumes from the journal; do not manually delete collection records.
Publication failure before journal replacement leaves the prior state intact.
After replacement the refresh is accepted, even if a later write fails. A hard
termination or disk failure can leave result.json behind the journal; use status
for checkpoints and retry ordinary collect to rebuild the result.

`save` exports the original execution conditions with the accepted collector
settings. Original source observations and their limitations still apply.

## Verification

The implementation was exercised with Python 3.12.14 / PyYAML 6.0.3 / pytest 9.1.1
and Python 3.10.19 / PyYAML 5.4.1 / pytest 9.0.3. Commands from the repository root:

```sh
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/mb-normal/bin/python -m pytest -q
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/mb-compat/bin/python -m pytest -q --ignore=tests/test_cli_aliases.py
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/mb-normal/bin/python tools/check_lifecycle_mutations.py
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/mb-compat/bin/python tools/check_lifecycle_mutations.py
```

The compatibility exclusion is the existing two tomllib registration tests.
Directed coverage checks post-run collector addition, artifact reporting,
unchanged execution evidence, final-result skipping without refresh, non-collector
change rejection without writes, PENDING continuation after another replan,
interruption after one completed Job, save export, and injected atomic-publication
failure. The CLI journey runs from another directory and parses JSON stdout.
Both environments detect all four existing lifecycle mutations. The advanced
CLI tutorial also completes. Publication failure is injected; actual disk-full,
remote filesystem outages and external simulator environments are not reproduced.
