# Review: unused workspace creation in the command adapter

## Finding

The standard command adapter executed Jobs from the saved invocation directory
and stored command logs under runs. Nevertheless, prepare created workspace/exec,
and the adapter's setup hook called mkdir for that same directory again.
There was no consumer of this directory in the standard command path.

The code was harmless on repeat execution, but it added an unexplained directory
and made an empty adapter hook look like a necessary preparation stage.

## Why the review missed it

The earlier reviews checked successful lifecycle transitions, failure recovery,
source-edit preservation and custom-adapter contracts. They did not trace each
created resource to an actual consumer in the standard user workflow.
Passing tests showed the implementation could run, not that every operation was
necessary. Idempotent mkdir concealed the redundancy: it caused no failing test.
We also explained the generic adapter interface before checking what the concrete
command implementation did, making a small implementation detail sound essential.
These are gaps in our review approach, not evidence that users needed this step.

## Correction

- Command setup has no filesystem side effects; the interface method is retained
  because ExecutionAdapter requires it.
- Prepare creates exec only for custom adapters, preserving their existing contract.
- The adapter_workdir path remains in context for compatibility; its presence in
  metadata does not assert that the standard command adapter uses or creates it.
- Existing directories are preserved. YAML setup Jobs and their failure gate are
  unchanged; whether setup should be a separate user cycle is a separate decision.

## Checks for future reviews

For each lifecycle step, identify its inputs, files written and concrete consumers.
Check the minimal command-only path before describing extension hooks. Ask whether
removing a side effect changes observable required behaviour. Separate interface
obligations from useful work performed by the implementation. Cover resource
ownership with behavioural checks: command-only prepare/setup/run succeeds without
exec, custom adapters still receive their workspace, and existing user files survive.

## Executable follow-up

[Lifecycle responsibility tests](../Lifecycle_Testing.md) turn the review findings
into absence/preservation assertions, forbidden side-effect checks, repeated
operation checks, and a targeted mutation check. Four seeded regressions verify
that the relevant tests fail; this is evidence of sensitivity to known faults,
not proof that every remaining operation is necessary.
