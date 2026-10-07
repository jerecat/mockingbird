# ADR 0013: Adopt execution edits at plan

Status: accepted, 2026-10-07

## Context

First-use feedback exposed unnecessary prepare cycles after editing arguments.
Running an old plan silently is also surprising when the YAML has changed.

## Decision

- Prepare owns source acquisition, paths, setup, scheduler and adapter selection.
- For the standard command adapter, plan reads current execution intent and
  freezes it with resolved Jobs. It preserves the prepared context, source
  evidence, working directory and successful setup state.
- Run compares normalized YAML execution intent with the plan's input before
  creating a run or invoking a capacity provider. Comments and mapping order
  do not affect this comparison. Lists retain order. No script hashes or diffs.
- On changed execution, interactive CLI run asks whether to update the plan and
  run, default yes. Declining or EOF cancels. Invalid answers prompt again.
  Non-terminal input and core API calls raise an actionable plan prerequisite.
  Validation failure never falls back to the old plan.
- Missing plans require explicit plan. Sources/setup/scheduler/name/path changes
  require prepare. Adapter changes and custom adapter config require prepare and
  setup because a custom hook may depend on its configuration.
- A run saves its own context with the planned execution config. Later edits do
  not affect collection of that run. Collect/status stay independent of replanning.
- Existing contexts/plans are supported: preparation fields are reconstructed
  from recorded evidence, and plans without execution input use the prepared
  execution config as their baseline.

## Consequences

The normal edit loop is YAML execution edit -> plan -> run. Run never silently
uses an outdated execution configuration. Interactive replanning is an explicit
CLI convenience; core does not prompt, acquire sources, or run setup implicitly.
A run still starts a new selected sequence and does not resume interrupted Jobs.
Concurrent workspace lifecycle operations remain unsupported.
