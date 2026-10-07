# CLI onboarding review: 2026-10-07

## What exposed the gap

After the CLI output fixes, the user still had to ask where URL/branch settings
live, where prepare clones sources, what `.reg` means, which directory commands
run in, and how an existing Git worktree connects to run/collect. A complete YAML
example did not answer these questions on its own.

## Why the previous review missed it

- We treated facts present somewhere in the repository as adequate documentation.
  The answer required reading README, contracts, and ADRs in combination.
- We started with MB's schema and defaults rather than the user's existing shell
  command. Source acquisition, execution paths, and collection identity appeared
  together before their separate purposes were explained.
- The review covered terminal formatting, error recovery, and successful sample
  execution. It did not ask the reader to predict cwd, argv, and output paths
  before executing a new project integration.
- The sample scripts already knew where to put results. Their passing tests did
  not demonstrate that a new user could create that agreement independently.
- The conversation loosely described cwd as the current invocation directory.
  The implementation uses the invocation directory saved at prepare time. We
  should have verified this boundary before explaining it.

These were review and explanation failures, not missing user input. More tests
of the same prepared example would not have addressed the missing mental model.

## Changes

Add a progressive guide: shell command -> one explicit Job -> matching collector
-> defaults -> directory ownership -> optional source acquisition. Link it from
README and Getting Started before the contract reference. Clarify the distinction
between adapter utility defaults and the declarative command adapter's cwd.
Extend the CLI review skill with a documentation-only prediction exercise.

## Completion criterion for future reviews

Using only the introductory guide, a reader should be able to identify:

1. The exact argv and cwd for a Job and its collector.
2. The clone destination, or why no clone is needed for an existing worktree.
3. Which files MB owns and which the project scripts own.
4. How producer and collector identify the same run/Job.
5. Which edits require prepare/setup/plan, and what an existing checkout preserves.

Then run the documented sequence in a clean temporary directory and compare those
predictions with evidence. Use an existing-worktree scenario as well as the
packaged tutorial. Keep technical correctness, execution verification, and
first-reader understanding as separate review questions.
