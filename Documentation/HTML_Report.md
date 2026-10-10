# HTML reports

`mb report PLAN` reads saved runs and writes a standalone interactive HTML file.
It does not execute Jobs, invoke collectors, refresh results, or load the current
confirmed plan. Open the printed path in a browser; no server or CDN is needed.
The default destination is `report.html` beside the plan's `runs` directory.
Regenerating replaces that HTML snapshot. Use `--output` to preserve another copy.

```sh
mb report soc-nightly
mb report soc-nightly --last 10
mb report soc-nightly --since 2026-10-01 --until 2026-10-10
mb report soc-nightly --last 10 --exclude-run RUN_ID
mb report soc-nightly --run RUN_ID_1 --run RUN_ID_2 --output review.html
```

All filters intersect. Exact run IDs are repeatable; unknown IDs fail rather than
silently disappearing. Dates include the whole day in the report-generating
machine's local timezone, using run start time. Exclusions precede `--last`.
The default includes all saved runs. Empty selections fail with an explanation.
Excluded runs are not embedded in the HTML.

## Evidence and comparison

- `run.json` identifies each run and its selected Job IDs.
- `result.json` supplies the latest collected states, verdicts, reasons and artifacts.
- The run's own `plan.json` supplies original Job definitions.

Run/plan identity and selected ID sets are checked before rendering. A mismatch
fails generation. A missing result means uncollected, not PASS or absent.
The history matrix uses the union of selected IDs across included runs. A dash
means not selected in that run. PENDING, UNCOLLECTED, collection ERROR, and final
ERROR remain distinct. PASS percentages use each run's selected count, including
unresolved and skipped Jobs; an empty selection displays no percentage.

Comparison uses the preceding included run, not an excluded run. Only common IDs
can recover or newly fail. Different saved payloads are marked Definition changed;
this is not proof that unchanged commands, source files or test intent are identical.
`collect --refresh` updates results for the same run; regenerate the HTML to show
those updates. The report does not reconstruct past collect attempts. Refreshed
collector configuration does not rewrite the original execution definition.

The report embeds artifact paths as supplied; Copy path copies them verbatim.
It does not copy or open artifact files. Browsers can restrict clipboard access;
a manual-copy message is shown when both clipboard methods fail.
Treat an HTML report as a copy of its included data when sharing it.

## Presentation

`src/mockingbird/report.html` contains the standard CSS, HTML and JavaScript.
Edit its CSS variables for colors and spacing without changing collection logic.
It is packaged with the Python module. No theme system or runtime dependencies
are added. Large histories increase HTML size and matrix rendering cost; use
`--last` or a date range to keep reports focused.

## Verification

Directed tests cover changing selected sets, absent results, refreshed verdicts,
collection versus final errors, identity mismatches, inclusive dates, exclusions
before last-N, unknown IDs, empty selections, script-closing text, and preservation
of source evidence. Live execution state is intentionally read from saved records;
report generation is not a transaction across concurrent run/collect processes.
Each JSON read is an atomic snapshot under the existing writer contract.

Implementation verification (2026-10-10): full suite passed on Python 3.12.14 /
PyYAML 6.0.3 / pytest 9.1.1 (367 tests), and Python 3.10.19 / PyYAML 5.4.1 /
pytest 9.0.3 (365 tests, only existing `test_cli_aliases.py` exclusion).
An isolated CLI `all -> report --last 1` journey generated a real PASS report;
Node syntax checking passed for its embedded script. Browser layout and actual
clipboard permissions remain unverified. No lifecycle responsibilities changed.

## Output example

Download [report-sample.html](examples/report-sample.html) and open it locally in a
browser (GitHub's file viewer displays source). This fictional SoC example contains
six runs, changing Job sets, a recovered failure, new failures, a definition change,
and distinct pending/uncollected/collection-error states. Every path is synthetic;
no actual test evidence or private environment paths are included.

Regenerate it from the repository root with:

```sh
PYTHONPATH=src python tools/generate_report_sample.py
```

The generator uses the production report renderer with temporary JSON fixtures.
It does not register a plan, run commands, or invoke collectors.
