# Setup command contract and retry workflow

A project can supply three external contracts:

| Phase | Contract | Success means |
| --- | --- | --- |
| setup | Ordered command list with finite timeouts | Every command exits zero and the adapter setup hook returns |
| run | Ordered Job list | Execution evidence is saved; exit codes are not test verdicts |
| collect | Per-Job collector command or no-check | A final judgement or an unresolved outcome is recorded |

Setup is synchronous preparation. It does not use collectors, infer PASS/FAIL test
judgements, or submit asynchronous preparation for MB to track. If a preparation
script submits external work, the wrapper must wait for completion before exiting
zero. Compile/build can still be an ordinary run Job when it belongs in every run.

## Define setup next to execution

```yaml
setup:
  defaults:
    args: []
    timeout_s: 600
  jobs:
    - id: configure
      command: [sh, ./configure.sh]
    - id: build
      command: [make]
      args: [simv]
      timeout_s: 3600
```

This is a top-level section, alongside `execution`, `sources`, and `scheduler`.
Setup accepts `defaults` and `jobs`. Each Job has a unique `id`, a non-empty
`command` argv list, optional `args`, and a finite positive `timeout_s`. A string
Job is shorthand for its ID. Per-Job fields replace defaults; arrays are replaced
whole. As with run, omitted args becomes `[job_id]`; use `args: []` for no arguments.
Unknown fields, duplicate IDs, invalid timeouts, and `collect` in setup are rejected.

Prepare resolves and validates the complete setup list before any source acquisition.
The resolved contract is saved in context.json. Plan does not execute setup commands.
Setup executes the list serially, stopping at the first nonzero exit, timeout,
launch error, or interrupt. It does not use the run capacity gate. Commands execute
in the invocation directory saved at prepare time; scripts can explicitly `cd`
into their source/worktree. They receive `MB_SETUP_ID` for this attempt and
`MB_JOB_ID` for the setup Job. MB does not supply a run ID for setup.

Top-level setup commands are independent of the execution adapter. After the
commands succeed, the existing Python adapter's `setup(context)` hook runs.
Custom adapters retain their hook requirement even without a top-level command
list. Their hooks should raise on failure and remain synchronous.

## Lifecycle and invalidation

```sh
mb prepare regression.yaml
mb setup regression.yaml
mb plan regression.yaml
mb run regression.yaml
mb collect regression.yaml
```

For the built-in command adapter, omitted setup (or an empty list) means no setup
is required: use `prepare -> plan -> run -> collect`. Explicit `mb setup` reports
that no setup is needed. Recovery instructions skip it. Existing custom adapters
still require setup; their interfaces have not changed.

Starting an actual setup attempt invalidates earlier setup success and removes
the old plan **before** running any command or hook. Until that attempt succeeds,
plan and run are blocked. After success, create a new plan before running.
Re-running setup is always explicit; plan/run do not automatically execute it.
Previous completed runs remain independently collectable.

## Fail -> edit -> setup again

If a setup command fails:

1. Read the reported Job and log directory.
2. Edit the project script or source to fix it.
3. Run `mb setup regression.yaml` again. The full setup list starts at the first
   Job; there is no automatic resume, rollback, source reset, or cleanup.
4. After success, run plan and run.

Previously successful setup Jobs may execute again. Make setup scripts repeatable
or have them detect already prepared outputs themselves. Partial outputs and user
edits remain in place; MB does not undo them.

Script/source content edits do not require prepare. **YAML contract edits do**:
run prepare again to adopt changed commands, arguments or timeouts, then setup
and plan. Saved context freezes the contract, not source/script contents.

Each attempt has a unique directory under:

```text
<workspace>/.reg/setup/<setup-id>/
  context.json
  setup.json
  jobs/<safe-job-directory>/execution.json
  jobs/<safe-job-directory>/logs/stdout.log
  jobs/<safe-job-directory>/logs/stderr.log
```

setup.json records RUNNING/SUCCEEDED/FAILED/INTERRUPTED and completed Job IDs.
Per-command execution.json includes the resolved contract, timestamps, and process
observations or an error. Retry creates a new attempt, preserving previous logs.
Hook failures are recorded in setup.json; custom hook I/O remains adapter-owned.
The workspace state points to the latest attempt. `mb status` remains a run-status
command, not a setup-status command; inspect the attempt path printed by setup.

A hard kill can leave RUNNING recorded. It cannot unlock plan/run. Before retrying,
ensure prior preparation processes have stopped. Concurrent operations in the
same workspace remain unsupported.

## Runnable failure-and-retry example

From the Mockingbird clone, after installing it:

```sh
mb prepare examples/setup-commands.yaml
touch work/setup-demo/force-setup-failure
mb setup examples/setup-commands.yaml
```

The second setup Job deliberately exits 7. MB reports failure and the saved logs.
Plan/run are blocked. The example's run Job uses no-check; that policy cannot
turn a failed setup into success.

Remove only the sample failure marker, then retry:

```sh
rm work/setup-demo/force-setup-failure
mb setup examples/setup-commands.yaml
mb plan examples/setup-commands.yaml
mb run examples/setup-commands.yaml
mb collect examples/setup-commands.yaml
```

In a real project, this step could instead be an editor fix to the script or source.
The retry starts from check_environment again and writes ready.txt on success.
Both setup attempts remain available for comparison. Cleanup is manual; removing
work/setup-demo also removes its attempt logs and any user edits there.
