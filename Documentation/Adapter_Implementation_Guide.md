# Adapter Implementation Guide

This is the advanced implementation guidance for project-owned
`ExecutionAdapter` code.

Most users should not write an adapter. Start with `Execution_Contract.md` and
the built-in declarative command path. Use this guide only when that small
contract is genuinely insufficient.

## 1. Choose the Job boundary first

`Job` is **not defined as a testcase**. It is:

> the smallest independently schedulable unit that is useful to rerun by the
> same stable identity.

Valid examples include:

```text
1 C testcase
1 UVM test + seed
100-test batch
1 formal property group
1 board boot + scenario
1 compile/elaboration unit
```

The important consequence is `--failed-from`: rerun granularity is exactly Job
granularity. If a Job contains 100 tests, FAIL rerun schedules that 100-test Job
again. The orchestrator deliberately does not split it.

### Job ID rules

A Job ID is the rerunnable identity, not an invocation identity.

Required by core:

- non-empty string;
- unique in one plan;
- no leading/trailing whitespace;
- no control characters;
- JSON-serializable Job payload/metadata.

Strong recommendations:

- stable for the same logical Job across runs;
- human-readable where practical;
- do not include timestamp, PID, temporary path, or run ID;
- include a seed if the seed defines a different rerunnable unit.

Good:

```text
pcie/dma/write/seed-001
smmu/s1/tlb-invalidate/cpu3
formal/coherency/property-group-a
```

Bad:

```text
test_20261007_051122_38491
/tmp/run123/test7
```

## 2. ExecutionAdapter contract

```python
class Adapter(ExecutionAdapter):
    def probe(self, context): ...
    def setup(self, context): ...
    def plan(self, context): ...
    def execute(self, context, job, execution): ...
    def collect(self, context, executions): ...
```

### probe

Use it for cheap, non-destructive integration checks:

- executable/tool available;
- license/query endpoint reachable if safe;
- board controller reachable;
- required project configuration exists.

Return `CheckResult` objects. Do not perform a full regression here.

### setup

Top-level declarative setup commands, when present, run before this hook. A custom
adapter still requires its setup hook even without those commands. Starting a
setup attempt invalidates previous setup success and its plan; raise on failure.
Command logs are recorded by MB; custom hook I/O remains adapter-owned.
See [Setup Contract](Setup_Contract.md).

Prepare reusable prerequisites. It should be safe enough to call repeatedly.
The conformance kit calls it twice intentionally.

Examples:

- generate project configuration;
- compile common testbench if that is project policy;
- create shared runtime assets.

### plan

Return canonical `Job` objects. Core interprets only `Job.id`; `payload` is
adapter-owned opaque JSON-serializable data.

Calling `plan()` twice under the same frozen context should return the same Job
IDs in the same order.

### execute

Core supplies a per-job `ExecutionContext`:

```text
execution.run_dir
execution.job_dir
execution.workdir
execution.artifact_dir
execution.logs_dir
execution.stdout_path
execution.stderr_path
```

Write temporary/job-private state under `workdir`, durable project artifacts
under `artifact_dir`, and logs under `logs_dir`.

Return `JobExecution`. Do not decide canonical PASS/FAIL here unless your adapter
naturally records that as opaque observation; normalization belongs in `collect`.

### collect

Return one outcome for each requested execution. If the result is final, return
`TestResult` with one canonical status:

```text
PASS
FAIL
ERROR
SKIP
```

Use `FAIL` for a test that ran and found a verification failure. A final
`TestResult` with `ERROR` is a project-defined terminal judgement, for example
an unrecoverable execution failure. It is retained and not recollected.

If a result is not ready, return `CollectionAttempt` with state `PENDING`.
If collection itself fails, return `CollectionAttempt` with state `ERROR`.
Both are unresolved outcomes and are retried in a later collect cycle.
Core also records collector exceptions or invalid responses as collection errors.
See the schema 2 examples below. Execution return codes are evidence; only the
project-owned collector decides whether they imply a final test result.

The minimum collected result contract is `Job ID + canonical status + list[str]`
artifact references. Artifact references are opaque; they are often paths, but
Mockingbird does not require or interpret that.

For the common case:

```python
from mockingbird.adapter_utils import execution_path_refs, result_from_execution

def collect(self, context, executions):
    results = []
    for execution in executions:
        # Project-owned interpretation.
        rc = int(execution.observation["returncode"])
        status = "PASS" if rc == 0 else "FAIL"
        results.append(
            result_from_execution(
                execution,
                status,
                artifacts=execution_path_refs(execution, "stdout", "stderr"),
            )
        )
    return results
```

For VCS, board tests, or another system, keep exactly the same envelope and
replace only the project-owned interpretation/artifact discovery. The helpers do
not parse logs, discover waveforms, or decide PASS/FAIL; they only remove
repetitive Mockingbird plumbing.


### One common collector with small exceptions

Hundreds or thousands of Job IDs should not imply hundreds of collector
implementations. Prefer one common rule and register only genuine exceptions in
project code:

    COLLECTOR_EXCEPTIONS = {
        "pcie/special-reset": reset_collector,
    }

    def collect_one(execution):
        collector = COLLECTOR_EXCEPTIONS.get(
            execution.job_id,
            default_collector,
        )
        return collector(execution)

    def collect(self, context, executions):
        return [collect_one(item) for item in executions]

Exact IDs are only one project-side option. A project may route by its own
payload, metadata, naming convention, or test group.

Mockingbird does not provide or interpret an exception registry. Keep routing
policy in the project unless repeated real integrations prove a common helper is
worth adding.

## 3. Process execution guidance

For normal Linux subprocess-based adapters, prefer:

```python
from mockingbird.adapter_utils import run_process

process = run_process(
    argv,
    execution,
    timeout_s=3600,
    env=my_explicit_environment,
)
```

The utility intentionally enforces the recommended pattern:

```text
shell=False
stdin=/dev/null
stdout -> file
stderr -> file
start_new_session=True
timeout -> SIGTERM -> grace -> SIGKILL for the process group
```

### Do not capture large stdout/stderr

Avoid:

```python
subprocess.run(..., capture_output=True)
```

for regression payloads. Simulator output can be extremely large. Canonical
JSON should contain paths/references and small metadata, not complete logs.

Recommended evidence:

```json
{
  "returncode": 1,
  "timed_out": false,
  "stdout_path": ".../stdout.log",
  "stderr_path": ".../stderr.log"
}
```

### Avoid shell=True

Do not build strings such as:

```text
source setup.sh && simv ... | tee run.log
```

inside generic adapter Python. Prefer a project-owned wrapper script if shell
semantics are genuinely required:

```python
["./run_test.sh", "--test", test_name]
```

This keeps quoting, environment setup, and simulator policy in the project that
owns them.

### Environment

An explicit `env` mapping is recommended for reproducibility. Credentials and
secrets must not be copied into context/result JSON. Authentication should remain
an external runtime concern.

## 4. Artifact guidance

Adapters should not put large binary/log payloads inside `JobExecution`.
Use files and record references/metadata only.

Suggested use:

```text
work/       disposable per-job runtime state
artifacts/  waveforms, coverage shards, summaries, generated ELF, etc.
logs/       stdout/stderr and textual logs
```

## 5. Conformance before real regression

Run:

```bash
mockingbird doctor regression.yaml
```

and add project-side tests using `mockingbird.testing`. See
`Adapter_Conformance_Testing.md`.


## Repeatable collection contract (schema 2)

Core calls collect with one unresolved execution at a time, in selected order.
Return exactly one matching TestResult or CollectionAttempt:

```python
from mockingbird.models import CollectionAttempt, TestResult

# Not available yet; no final TestResult exists.
CollectionAttempt(execution.job_id, "PENDING", reason="not ready")
# Collection failed; retry in a later cycle.
CollectionAttempt(execution.job_id, "ERROR", reason="service unavailable")
# A final project judgement; this is never recollected.
TestResult(execution.job_id, "ERROR", reason="project-defined terminal error")
```

Exceptions, malformed outcomes, and ID mismatches become collection errors.
Completed results survive later collect calls. Collectors must tolerate retries.
Core attaches the frozen Job to execution.contract and the run identity to
execution.run_id. These are JSON-serializable evidence, not scheduler semantics.
The declarative adapter uses the saved contract and MB_JOB_ID/MB_RUN_ID external
protocol; custom adapters remain free to interpret their own opaque payloads.
Old examples returning final TestResult are still valid. Final result interpretation
is the adapter author's explicit policy, never the generic executor's policy.
