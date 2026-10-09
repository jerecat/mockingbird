# ADR 0017: Separate execution records from collection results

Status: accepted, 2026-10-09

Users need one clear place to inspect each concern. Run records previously held
copied collection state and verdicts, while result records duplicated final
verdicts in both tests and collection entries. Collect also rewrote run.json.

Run owns run.json. Collect owns result.json and recovery checkpoints, and never
writes run.json, even when collecting historical runs. Plan/run schemas stay 3;
result schema becomes 4. Result keeps identity and run start time for independent
quality timelines, but execution finish/duration belong in run.json only.

Result has one jobs mapping containing collection state, attempts, observation
time and an optional final result. Final result payloads and collector contracts
are unchanged. Summary is a derived convenience; detailed results are not copied
into a second list. The existing COMPLETE/PENDING/ERROR/UNCOLLECTED collection
states remain distinct from final PASS/FAIL/ERROR/SKIP verdicts.

FAIL selection accepts historical tests arrays and new jobs entries. Recollecting
old runs publishes schema 4 without rewriting their run.json; historical copied
collection fields are stale legacy fields, not authoritative. CLI status continues
to inspect checkpoints for progress when a collection sweep was interrupted.
External result consumers must migrate to jobs; see Record_Formats.md.

Verification: Python 3.12.14 / PyYAML 6.0.3 / pytest 9.1.1 passed 335 tests;
Python 3.10.19 / PyYAML 5.4.1 / pytest 9.0.3 passed 333 tests with only the
existing CLI-alias exclusion. Both detected all four lifecycle mutations. The
advanced guided tutorial completed. Tests check result field ownership and
absence of duplicate verdict lists, run.json byte/mtime stability and a write
guard during repeated collect, and FAIL selection from old/new result formats.
