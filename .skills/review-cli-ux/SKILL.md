---
name: review-cli-ux
description: Review and improve Mockingbird CLI usability through real user journeys. Use when adding or changing commands, output, lifecycle prerequisites, errors, progress, status, tutorials, or recovery behavior.
---

# Review CLI UX

Start from what the user knows at the terminal. Read the relevant command,
lifecycle checks, and tutorial; then run the commands in an isolated workspace.
Do not judge usability from unit tests or implementation code alone.

## Check each journey

- Start from a fresh checkout. Try `run` before `prepare`, after `prepare`, and
  after `setup`. Follow the printed recovery commands literally. Ensure they
  include the definition path, quote spaces, and avoid repeating completed work.
- Exercise `prepare -> setup -> plan -> dry-run -> run -> status -> collect` and
  `all`. Check help, selection, and explicit run-directory targeting.
- Try missing files, malformed YAML, invalid configuration, unknown Job IDs,
  missing/stale prerequisites, and a nonexistent run directory.
- Exercise mixed PASS/FAIL/ERROR/SKIP, PENDING, malformed collector output, and
  retryable collection errors using the mock simulation tutorial. Inspect
  status before collection and after retrying unresolved Jobs.
- Interrupt execution and collection. Inspect saved evidence; check that the
  guidance does not imply unstarted Jobs can be recovered by collect.
- Inspect stdout, stderr, exit code, and the next command together. Parse JSON
  modes with a JSON parser. Check unequal Job ID lengths and multiline reasons.

## Review the first-reader explanation

Read the introductory guide without relying on implementation knowledge. Before
running anything, write down the exact argv and cwd for run and collect, clone
destination, MB-owned paths, project-owned results, and run/Job identity linkage.
If these answers require searching contracts or ADRs, improve the entry guide.

Start examples with a familiar shell command, then one explicit Job, then its
collector, and only then defaults. Explain each new field when it becomes needed.
Exercise an existing worktree with `sources: []` as well as source acquisition.
Verify that choosing a script path does not imply `cd`, and distinguish cwd saved
at prepare time from a later CLI invocation. Explain when YAML edits require
prepare/setup/plan and why source edits are not snapshotted.

Execute the guide in an isolated directory and compare the evidence with those
predictions. Passing a preconfigured tutorial is not proof that a new user can
connect their own scripts. Record discovered explanation gaps and their causes;
keep the preventive checks in this skill rather than accumulating incident prose.

For guided commands, verify cancellation before and after file creation, refusal
of existing directories/symlinks, preservation of exercise files, and shell-quoted
cleanup instructions limited to the created directory. Use normal CLI paths.
Explain intentional nonzero outcomes before running them, verify resulting state,
and stop on genuine failures rather than continuing a misleading success tour.

Keep the default tutorial focused on the smallest complete user workflow with
a clear finishing point. Label repeated commands by their different purpose.
Move fault injection into an optional advanced path; keep idempotence proofs in
tests rather than mandatory repeated user steps. Explain which actions simulate
external work, so sample helpers are not mistaken for product repair commands.

For preparation changes, exercise setup failure -> script/source edit -> setup
retry -> plan -> run. Preserve each attempt's logs and partial outputs, invalidate
old success before retry, and check that failed/incomplete setup blocks old plans.
Distinguish live script edits from frozen YAML contracts. Do not require empty
setup steps for the standard command path; keep custom adapter hook semantics.

## Apply these rules

1. Answer: what happened, what needs attention, and what the user can do next.
   Explain prerequisites without a Python traceback. Keep tracebacks available
   through `--debug`; do not disguise unexpected failures as success.
2. Default to concise human output. Keep internal context/configuration JSON in
   saved files or explicit `--json` output. Do not leak progress into JSON stdout.
   Summarise repeated successful diagnostics by user task. Keep implementation
   names and executable paths in details, while retaining every failure/warning
   and its cause in normal output. Say exactly what a passed check establishes:
   finding an interpreter does not validate its script or mean a Job has passed.
3. Align comparison columns. Keep long diagnostic details behind an explicit
   option. Include paths that let users find saved evidence.
4. Show progress before slow phases and flush transitions. Avoid polling spam.
5. Distinguish execution records, collection attempts, and final verdicts.
   Final ERROR is not a retryable collection error. Command completion is not
   external completion; recorded RUNNING is not proof of current liveness.
6. Preserve serial execution, no-check semantics, and collector contracts.
   Do not auto-prepare, reset sources, rerun Jobs, or erase user edits to make
   an error disappear. Recovery guidance must preserve user control.
7. Keep lifecycle preconditions structured and presentation in the CLI. Avoid
   parsing exception text to decide which recovery steps to recommend.
8. Update English help/tutorials alongside behavior. Add regression tests for
   meaningful journeys and negative cases, not snapshots of every cosmetic line.

Before finishing, show representative terminal output and report tested journeys,
remaining limitations, and any machine-output compatibility changes. Use this
repository skill directly; do not claim `.skills/` is automatically discovered
by every Codex installation.

## Review visual grouping

Inspect complete terminal transcripts as well as individual messages. Separate
phase/Job transitions, summaries, and next actions with one blank line. Keep a
Job's completion and evidence together; indent supporting paths and every line
of multiline details. Keep table rows compact and separate the table from prose.
Check composed `all` and tutorial flows for missing or duplicated spacing, and
verify stderr recovery and redirected output. Do not reformat child output,
JSON documents, or saved logs to achieve human-output spacing. Avoid snapshots
of every cosmetic line; exercise meaningful journeys and machine contracts.
