# Architecture Contract

This document defines constraints that should be treated like API compatibility rules.

## AC-1: Core is execution-detail blind

Files directly under `src/regorch/` may orchestrate lifecycle, evidence, selection, and scheduling. They must not import concrete implementations from:

```text
regorch.adapters.*
regorch.sources.*
regorch.capacity.*
```

They also must not spawn project commands directly.

Enforced by:

```text
tests/test_core_boundaries.py
tests/test_core_isolation.py
```

## AC-2: Project execution crosses only ExecutionAdapter

Core sees jobs and observations as opaque data. Only an `ExecutionAdapter` may interpret a command, simulator output, board response, or project-specific PASS/FAIL rule.

Required methods:

```text
setup(context)
plan(context)
execute(context, job)
collect(context, executions)
```

## AC-3: SCM semantics cross only SourceProvider

Core may request materialization but may not know checkout/update command details. Git and SVN are bundled implementations, not core concepts.

Required method:

```text
materialize(source, destination)
```

## AC-4: Load semantics cross only CapacityProvider

Core does not know queue names, farm commands, host-load formulas, or scheduler brands.

Required method:

```text
available_slots() -> int
```

## AC-5: Human intent and machine evidence are separate

```text
regression.yaml   human-authored intent
context.json      resolved/frozen context
plan.json         discovered canonical plan
run.json          selected/executed run evidence
result.json       canonical result evidence
```

Generated JSON must not be used as a hand-edited configuration format.

## AC-6: FAIL rerun has explicit provenance

A FAIL-only rerun must name the previous result/run directory. No implicit `latest failed` behavior is part of the architecture.

The new run records the selected source evidence, including the previous result identity/hash.

## AC-7: External integration must not require core modification

The loader accepts `module:Class` plugins. A project may therefore own its adapter/provider package separately and install it into the same Python environment.

Example:

```yaml
execution:
  adapter: company_soc.regression:Adapter
```

Enforced by `tests/test_architecture_contracts.py`.

## Change rule

If a proposed change violates an AC rule, either:

1. redesign the change to preserve the contract; or
2. write an ADR explicitly replacing the rule and update the contract tests in the same change.

Do not silently weaken a contract test to make a feature pass.
