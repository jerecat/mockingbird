# ADR 0007: Declarative execution and bounded hand-off

Status: Accepted

## Context

The normal project already has commands that engineers type manually, often a
run.sh-style wrapper. Requiring every user to implement a Python
ExecutionAdapter duplicates that command interface and raises adoption and
maintenance cost.

Compute-center use adds two safety requirements:

- Mockingbird must never intentionally dispatch beyond declared capacity.
- Mockingbird must not become a resident workload manager after a project
  command hands work to an external scheduler.

The same design must still work for local workstations, QEMU, board runners, and
other command-line environments.

## Decision

The normal integration path is declarative execution in regression.yaml.

Users declare a project command, a finite local timeout, a list of Mockingbird
Jobs, and one collection contract.

A string Job ID is passed as the command's single argument. A mapping can supply
explicit argv and a Job-specific timeout.

One permitted Job starts one project-owned command. Mockingbird does not split
that command into compile, submit, or monitor phases.

Collection is explicit:

- exit-code mode for synchronous commands;
- one shared project-owned collector command for asynchronous or richer result
  interpretation.

Python ExecutionAdapter remains available as an advanced escape hatch.

Capacity remains a hard gate. At each scheduling decision, core computes the
allowed running count from min(max_parallel, available_slots()) and subtracts
locally in-flight execute calls before admitting new work. If capacity drops
below already-running work, existing executions are left alone and new dispatch
stops.

If an external system continues work after the local command returns, its
CapacityProvider must account for that handed-off work in later samples.

## Consequences

Most projects can integrate with YAML plus their existing shell/CLI wrappers.

The core remains execution-detail blind. Compute-center scheduler IDs and
submission semantics do not enter the canonical model.

The declarative executor enforces a finite local hold time and does not create a
resident monitoring process.

Asynchronous users normally separate run and collect rather than using all
unless their collector is valid immediately after submission.
