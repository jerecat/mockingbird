# Declarative Execution Contract

This is the normal project-facing execution interface.

The goal is simple:

> If a project can already be run from the command line, integrating it with
> Mockingbird should not require Python.

## Smallest useful contract

    execution:
      command: ["./run.sh"]
      timeout_s: 600
      jobs:
        - test_a
        - test_b
      collect:
        mode: exit-code

For each string Job entry, Mockingbird runs exactly one project command:

    ./run.sh test_a
    ./run.sh test_b

The command runs from the directory where Mockingbird was invoked. stdout and
stderr go to the Job's Mockingbird log files.

timeout_s is required. It is the maximum time Mockingbird may keep the local
project command. This value is project policy; Mockingbird does not invent one.

## Job-specific argv

Use a mapping when the Job does not use the simple command + Job ID form:

    execution:
      command: ["./run.sh"]
      timeout_s: 600
      jobs:
        - id: pcie_dma_001
          args: ["--test", "dma_write"]
        - id: long_compile
          args: ["--test", "compile_heavy"]
          timeout_s: 1800
      collect:
        mode: exit-code

The Job ID remains Mockingbird's only canonical identity. args are opaque project
arguments.

## Result collection

Collection is explicit. Choose one form.

### Synchronous command: exit-code

    collect:
      mode: exit-code

This declares that the project command's exit code is the result:

    0       PASS
    nonzero FAIL
    timeout ERROR

This mode is suitable when the command itself finishes the test.

### Project-owned collector command

For submit-and-return flows, use a project collector:

    collect:
      command: ["./collect.sh"]
      timeout_s: 30

Mockingbird calls the same collector once for each executed Job and appends the
Mockingbird Job ID:

    ./collect.sh pcie_dma_001

stdout must contain exactly one JSON object:

    {
      "status": "FAIL",
      "artifacts": [
        "artifact://pcie_dma_001/sim.log"
      ]
    }

status is PASS, FAIL, ERROR, or SKIP. artifacts is an optional list of opaque
string references. Optional reason and metadata fields are also accepted.

Collector stderr is available for diagnostics. Collector timeout, non-zero exit,
invalid JSON, or an invalid status becomes ERROR.

The collector may internally use one default judgement rule and a small
exception table. Mockingbird does not know or interpret that routing.

## Submit-and-return compute-center use

The executor does not stay resident to follow the external Job:

    Mockingbird
        |
        +-- ./run.sh test_a
                |
                +-- compile
                +-- submit
                +-- return
        |
        +-- local execute complete

The external scheduler owns the submitted work after hand-off. Mockingbird does
not require or record its scheduler Job ID.

For this flow, normally run:

    mb run regression.yaml
    # wait/check through the project's normal mechanism
    mb collect regression.yaml --run-dir runs/<chosen-run>

Do not use mb all unless the configured collector is valid immediately after the
project command returns.

## Capacity

Mockingbird dispatches only through the configured capacity gate:

    effective limit = min(max_parallel, available_slots())

If the gate is full, no new project command starts. Existing work is not killed
when capacity later drops.

For an external asynchronous scheduler, its CapacityProvider must account for
already submitted work in later samples. Mockingbird deliberately does not
become the scheduler.

## Advanced escape hatch

When this small contract is genuinely insufficient, an external Python
ExecutionAdapter remains supported.

That is the exception path. It is not the normal onboarding path.
