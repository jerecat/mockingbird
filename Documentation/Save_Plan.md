# Save a run as a new plan

`save` exports a YAML definition. It does not register a plan, acquire sources,
run setup, or execute Jobs.

```sh
mb save smoke --as smoke-repro --output plan/repro.yml
mb save smoke --run <run-id> --test test_a --as smoke-repro --output plan/repro.yml
```

`--as` and `--output` are required. Use a different, unregistered plan name.
The output directory must exist; an existing file or symlink is never replaced.
Without `--run`, save reads the latest-started run, just like status and collect.
Without `--test`, it exports all Jobs selected in that run, in saved plan order.
Repeat `--test` for multiple IDs. IDs not selected in the source run are errors.
This exports selected contracts, not only completed Jobs or only FAIL results.

The saved run's plan and observations are authoritative. Save does not read the
current YAML, inspect today's worktree, or invoke preparation/execution commands.
The command adapter exports fully resolved Job commands, arguments, timeouts,
collectors and metadata, plus the original setup, scheduler, sources and project
metadata. Dependencies between Jobs are not inferred; a selected Job may still
need build or preceding Jobs that the user must include.

Run-start checks inspect tracked files only (`tracked_dirty`); untracked files
are not scanned. Save always warns about this limitation for these records.
Older records using `dirty` remain readable.

Git source revisions are pinned to recorded run-start commits. Dirty observations
produce a warning on stderr and a comment in the YAML: uncommitted changes are
not included. Unknown observations also warn; absent run-start HEAD falls back
to the recorded preparation revision when available. A clean observation is
not a guarantee of reproducibility: ignored files, binaries, tool versions,
external inputs, seeds and edits during execution are not captured.

Review paths and environment-specific configuration before sharing. Paths and
source URLs are preserved literally, not automatically relocated. A commit must
be available from the repository accessible to the receiver. Use a fresh plan
name/workspace on the receiving side: prepare never resets existing source trees.

```sh
mb prepare plan/repro.yml
mb setup smoke-repro       # Only if configured
mb plan smoke-repro
mb run smoke-repro
mb collect smoke-repro
```

Other source providers retain their original settings with a warning unless they
implement `export_source(source, prepared, observation)`. This optional method
updates the exported source mapping and returns a list of limitations.
Custom execution adapters must implement `export_jobs(saved_jobs)` to return an
execution YAML mapping; otherwise save fails clearly instead of guessing how to
reconstruct opaque payloads. Both export hooks must be side-effect-free.
Schema-3 run/plan records are required; old schema-3 runs without observations
are supported with explicit unknown-state warnings.

## Verification

For this change, Python 3.12.14 / PyYAML 6.0.3 / pytest 9.1.1 passed
333 tests. Python 3.10.19 / PyYAML 5.4.1 / pytest 9.0.3 passed 331 tests,
with only the existing tests/test_cli_aliases.py exclusion. Both environments
detected all four lifecycle mutations. A receiver workflow acquired a real local
Git repository, preserved unrelated sources, ran optional setup and completed
plan/run/collect. Export was also exercised against the guided tutorial records.
Dirty/unknown warnings, historical selection, missing Jobs, unsupported adapters,
existing files/symlinks and injected write failure were checked. External farms,
private remote access and simulator/toolchain reproducibility were not tested.
