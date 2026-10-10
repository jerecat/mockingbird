# Idea: multi-plan HTML reports

Status: design note only; not implemented.
Date: 2026-10-10

## Intent

Combine several plans in one standalone HTML dashboard while keeping each plan's
Job identities and run history independent. The current `mb report` implementation
accepts one plan. The synthetic dashboard's plan selector illustrates the proposed
interaction; it is not evidence of multi-plan support in the CLI.

Keep this a thin presentation feature over saved records. Do not change run or
collect, merge stored results, execute collectors, or introduce a report server.

## Identity and presentation

- Identify a report row by `(plan name, Job ID)`. Identical Job IDs in different
  plans must not silently become one test or share a history.
- Show an overall summary and a plan selector; drill into each plan's runs.
- Select included runs first, then compute the union of selected Job IDs within
  each plan. Read each run's own `run.json`, `result.json`, and `plan.json`.
- Compare against the preceding included run of the same plan only.
- Preserve the distinction between absent, uncollected, pending, collection error,
  and final verdict. A missing Job in a run is not a recovery or SKIP.
- Use the existing single-plan detail view and artifact path copy action.
- Treat generated HTML as a snapshot. A later `collect --refresh` is reflected
  only after report regeneration, without changing run identity.
- Excluded run data must not be embedded in the generated HTML.

## Proposed CLI

Accept one or more positional plan names, preserving the single-plan invocation:

```sh
mb report soc-nightly
mb report soc-smoke soc-nightly --output overview.html
mb report soc-smoke soc-nightly --last 10
mb report soc-smoke soc-nightly --since 2026-10-01 --until 2026-10-10
mb report soc-smoke soc-nightly --exclude-run RUN_ID
mb report soc-smoke soc-nightly --run RUN_ID_1 --run RUN_ID_2
```

| Option | Proposed multi-plan meaning |
| --- | --- |
| `--last N` | Latest N matching runs **per plan**, after exclusions |
| `--since`, `--until` | Same inclusive local-date range applied to each plan's run start timestamps |
| `--run ID` | Include the specified run IDs only; repeatable |
| `--exclude-run ID` | Exclude the specified run IDs; repeatable |
| `--output PATH` | Destination for the combined standalone HTML |

If a supplied run ID exists in more than one requested plan, reject the ambiguous
selection rather than guessing. Keep unknown-ID errors. Do not add per-plan filter
syntax in the first implementation.

Proposed default destination: retain the existing destination for a single plan;
use `./report.html` in the caller's directory for multiple plans. Keep source-record
protection when validating an output path against all included plans.

## Questions to settle before implementation

- Define the overall summary explicitly. A useful candidate is each plan's latest
  included run, with per-plan timestamps visible. Do not sum every historical run
  and label that as the current result.
- Decide how to display a requested plan with no matching runs, including when
  explicit `--run` selections belong only to other requested plans. Do not silently
  hide an empty plan or imply it passed.
- Specify duplicate positional plan names and repeatable run-ID handling.

These are future design decisions, not changes to the current CLI contract.
