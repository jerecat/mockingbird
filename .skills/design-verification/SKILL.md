---
name: design-verification
description: Derive and execute evidence-based verification plans for software, hardware, firmware, CLI tools, and integrations. Use when planning verification, reviewing test completeness, validating changes, preparing a release, or investigating missed scenarios; cover requirements, normal behavior, boundaries, state transitions, faults, recovery, compatibility, and closure.
---

# Design Verification

## Establish the verification contract

- Identify the system under test, its boundaries, intended users, environment,
  dependencies, and authoritative requirements.
- Separate specified behavior from assumptions and unresolved design choices.
  Do not declare observed behavior correct merely because the implementation does it.
- State the claim being verified and its observable pass/fail criterion.
  Ask only about ambiguities that change that criterion; continue independent work.
- Scale effort to impact, uncertainty, and failure cost. Do not build a large
  framework when a small directed test gives decisive evidence.

## Derive a compact verification plan

Map each relevant requirement or invariant to:

| Requirement or invariant | Scenario and stimulus | Expected behavior | Observation and oracle | Method | Evidence or gap |
| --- | --- | --- | --- | --- | --- |

Derive cases before reading existing tests in detail. Then compare the plan with
existing coverage; distinguish absent tests from untested environments and absent
requirements. Keep the oracle independent of the implementation under test.
Use specified values, independent models, known vectors, or properties as appropriate.

Consider these dimensions and record material exclusions with a reason:

- Normal use: first use, repeated use, typical end-to-end user workflows.
- Inputs: empty, absent, malformed, duplicate, minimum/maximum, just outside
  limits, and representative equivalence classes.
- State and time: legal/illegal transitions, ordering, repeated operations,
  stale state, partial completion, cancellation, restart, timeout, and races.
- Resources and dependencies: disk/quota/inodes, permissions, missing tools,
  network/authentication, process failure, device disconnection, capacity,
  and unusually large or long-running work.
- Persistence and recovery: interrupted writes, commit boundaries, authoritative
  versus derived records, cleanup, retry, duplicate side effects, and ownership.
- Compatibility and integration: supported versions/platforms, real interfaces,
  configuration migration, and behavior across independently owned components.
- Performance and security only where requirements or concrete exposure warrant
  them; define measurable limits rather than inventing arbitrary thresholds.

For stateful systems, examine failures immediately before and after each
irreversible action or persistence boundary. Check what the operator can observe
and whether retry is safe. Include interactions between dimensions when they
can invalidate an invariant; do not enumerate the Cartesian product mechanically.

## Select and execute verification methods

- Prefer directed tests for precise requirements; use parameterization,
  properties, model comparison, randomized tests, or stress tests when justified.
- Use the smallest adequate level: unit, component, integration, or end-to-end.
  Include real user workflows where mocks cannot verify the contract.
- Keep fault injection bounded and isolated. Inject failures at actual I/O or
  dependency boundaries; never fill the user's disk or interrupt production.
- Distinguish injected faults from real resource exhaustion and report the limit
  of the evidence. Use realistic experiments when injection misses kernel,
  buffering, timing, hardware, or remote-service behavior.
- Observe exit codes, outputs, persisted state, process/device state, side effects,
  and subsequent recovery as relevant. An exception alone is not an adequate oracle.
- Preserve raw evidence needed to reproduce failures: version/configuration,
  commands, seeds, relevant records, and expected versus observed behavior.
- Run applicable project checks and required compatibility environments.
  Do not weaken assertions or skip failures simply to obtain a passing result.

## Review evidence and close

- Classify each material claim as verified, failed, unverified, or blocked.
  Report test coverage separately from functional/code coverage and from confidence.
- Investigate failures against requirements. Record unspecified behavior as a
  design gap; avoid silently turning it into a new normative contract.
- After a fix, rerun the reproducer and relevant neighboring cases.
  Broaden checks only when changes or unresolved risks justify it.
- Review whether tests would detect a plausible regression. Use a small mutation
  or independent review when useful; avoid tests that merely mirror code.
- Summarize what was verified, defects found, recovery limitations, exclusions,
  and remaining evidence needed. Test count or "all green" alone is not closure.
- Preserve a minimal reusable regression for consequential bugs.
  Update the verification plan when a missed dimension is discovered.

## Apply without inflating the design

Keep verification knowledge outside product flows unless it helps a user decide
what to do. Do not add runtime features solely to make testing convenient.
For an AI harness evaluation, evaluate the harness itself; distinguish that
evaluation from verification of an artifact produced by the harness.
