# Future extensions and a simple default workflow

Date: 2026-10-07
Status: design intent; no implementation scheduled

## Direction

Dependency handling, parallel/distributed execution and reproducible execution
environments are possible future extensions. Their absence today is a scope
decision, not a permanent prohibition.

Add them when a concrete operational need justifies the implementation and
maintenance cost. Do not build speculative configuration or abstractions now.

## Preserve the simple workflow

- A plain ordered Job list should continue to execute serially without requiring
  a dependency graph or distributed execution configuration.
- Only users enabling an advanced capability should need its additional settings.
- Defaults should keep reducing repetition while plan resolves a complete
  internal contract for each Job.
- Execution evidence, collection attempts and final results remain separate
  concepts linked to the Job within its run.

## Relationship to current decisions

[ADR 0009](../ADR/0009-serial-execution-policy.md) still enforces integer
`max_parallel: 1`. This note does not enable parallel execution. A future change
must revisit that ADR and define ordering, dependencies and failure behaviour.

[ADR 0011](../ADR/0011-reuse-user-managed-source-trees.md) permits user-managed,
mutable source trees. Future reproducibility support may offer an explicit mode
or integration without forcing the ordinary workflow to reject edits or collect
source diffs. Source-content tracking is not being added now.

Future extensions should preserve these simple defaults while making any new
guarantees, requirements and recovery semantics explicit.
