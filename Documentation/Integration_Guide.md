# Integration Guide

The normal Mockingbird integration is a contract, not a Python implementation.

New to the configuration? Start with [From shell commands to Mockingbird](From_Shell_to_Mockingbird.md)
for a runnable existing-worktree example and an explanation of directory ownership.

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
        mode: no-check

    scheduler:
      capacity_provider: fixed
      max_parallel: 1
      poll_interval_s: 1
      config:
        slots: 1

A string Job entry means command + Job ID. Use a mapping only when argv differs:

    jobs:
      - id: pcie_dma_write
        args: ["--test", "dma_write"]
      - id: compile_heavy
        args: ["--test", "compile_heavy"]
        timeout_s: 1800

## 2. Choose result collection explicitly

Without collect, the resolved contract uses no-check: PASS with no evidence
inspection. Choose an explicit project collector for checked results:

    collect:
      command: ["./collect.sh"]
      timeout_s: 60

Without collector args, the resolved args is [job_id]:

    ./collect.sh pcie_dma_write

Both commands receive MB_JOB_ID and MB_RUN_ID in the environment. The project
uses these to associate its external work/results. No external scheduler IDs
or directory layout are required by MB.

The collector prints one JSON object and exits zero:

    {"status":"PASS","artifacts":["artifact://pcie_dma_write/sim.log"]}

If results are not ready:

    {"status":"PENDING"}

Collector failures are collection errors, separate from final test judgements.
Repeated collect retries only unresolved Jobs and retains final results.

Common fields can be written under execution.defaults. Each Job can override
command, args, timeout_s and the entire collect mapping. Plan expands all defaults,
validates the full contracts, and freezes them. Unknown fields and invalid values
are rejected. args: [] explicitly requests no arguments.

## 3. Capacity is independent of execution

Local example:

    scheduler:
      capacity_provider: fixed
      max_parallel: 1
      config:
        slots: 1

Compute-center example:

    scheduler:
      capacity_provider: command
      max_parallel: 1
      poll_interval_s: 5
      config:
        command: ["./available_slots.sh"]

The capacity wrapper prints one non-negative integer.

For a runnable two-slot external queue demonstration, follow
[Serial submission with limited external work](Tutorial_Capacity_Gate.md).
It uses two terminals to show a third submission waiting and then resuming.

Normal operation uses max_parallel: 1: commands run one at a time in list order.
Capacity still gates each dispatch; zero pauses new execution. External work
may continue after a submission command returns. See ADR 0009.

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

Repeat this command later for PENDING/collection-error Jobs. Mockingbird does not
remain resident to poll the scheduler. mb all performs just one collection sweep;
if incomplete, continue collecting the same run explicitly.

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
    [ ] collector returns one final result or unresolved outcome per requested Job
    [ ] large logs remain files
    [ ] no secret is written into context/result/check messages

## Optional preparation commands

A top-level `setup.jobs` list can prepare the project before plan/run. Commands
run serially and must exit zero; failed attempts preserve logs and can be retried
after editing scripts or sources. See [Setup Contract](Setup_Contract.md).
Without setup commands, the built-in command adapter does not require a setup
cycle; the explicit setup command in the lifecycle above may be omitted.
