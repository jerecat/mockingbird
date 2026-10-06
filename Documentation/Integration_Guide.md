# Integration Guide

The normal Mockingbird integration is a contract, not a Python implementation.

## 1. Start from the command a human already runs

Suppose the project already supports:

    ./run.sh test_a
    ./run.sh test_b

Describe that directly:

    name: soc-nightly

    sources: []

    execution:
      command: ["./run.sh"]
      timeout_s: 900
      jobs:
        - test_a
        - test_b
      collect:
        mode: exit-code

    scheduler:
      capacity_provider: fixed
      max_parallel: 4
      poll_interval_s: 1
      config:
        slots: 4

A string Job entry means command + Job ID. Use a mapping only when argv differs:

    jobs:
      - id: pcie_dma_write
        args: ["--test", "dma_write"]
      - id: compile_heavy
        args: ["--test", "compile_heavy"]
        timeout_s: 1800

## 2. Choose result collection explicitly

For a synchronous command whose exit status is the test result:

    collect:
      mode: exit-code

For compile + submit + return workflows:

    collect:
      command: ["./collect.sh"]
      timeout_s: 60

Mockingbird appends the Job ID:

    ./collect.sh pcie_dma_write

The collector prints one JSON object to stdout:

    {"status":"PASS","artifacts":["artifact://pcie_dma_write/sim.log"]}

The same collector is reused for every Job. Project code may use a default rule
plus a small exception map internally; Mockingbird does not know that policy.

## 3. Capacity is independent of execution

Local example:

    scheduler:
      capacity_provider: fixed
      max_parallel: 8
      config:
        slots: 8

Compute-center example:

    scheduler:
      capacity_provider: command
      max_parallel: 20
      poll_interval_s: 5
      config:
        command: ["./available_slots.sh"]

The capacity wrapper prints one non-negative integer.

Mockingbird never intentionally dispatches above the reported gate. For
submit-and-return systems, the wrapper must account for already submitted
external work before more capacity is reported.

## 4. Compute-center lifecycle

The normal asynchronous sequence is:

    mb doctor regression.yaml
    mb prepare regression.yaml
    mb setup regression.yaml
    mb plan regression.yaml
    mb dry-run regression.yaml
    mb run regression.yaml

After the project/system says results are ready:

    mb collect regression.yaml --run-dir runs/<chosen-run>

Mockingbird does not remain resident to poll the scheduler. Do not use mb all
unless collection is valid immediately after run.sh returns.

## 5. Source integration

Built-in Git and SVN providers may be mixed in any count. Use a custom
SourceProvider only for a materially different materialization mechanism.

## 6. Advanced Python escape hatch

If the command contract cannot express a real integration requirement, an
external Python ExecutionAdapter is still supported:

    execution:
      adapter: my_soc_regression.adapter:Adapter
      config:
        profile: nightly

That path is deliberately advanced. See Adapter_Implementation_Guide.md and
Adapter_Conformance_Testing.md.

## Acceptance checklist

    [ ] doctor passes on a representative execution machine
    [ ] Job IDs are stable and unique
    [ ] timeout_s bounds every declarative project command
    [ ] one permitted Job starts one project command
    [ ] capacity never admits work above the declared gate
    [ ] async capacity query accounts for already handed-off external work
    [ ] collector returns exactly one canonical result per executed Job
    [ ] large logs remain files
    [ ] no secret is written into context/result/check messages
