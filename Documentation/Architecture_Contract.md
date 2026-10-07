# Architecture Contract

These rules protect **architectural meaning**, not accidental Python API shape.

Mockingbird's primary invariant is that the core does not understand the systems
it orchestrates. The core should remain small, simple, and inexpensive to
maintain. Project-specific knowledge stays outside it.

Exact argument names, method ordering, helper functions, and other v0.x API
shapes are not architecture invariants. They may evolve while these semantic
boundaries remain intact.

See `Design_Principles.md`.

## AC-1: Core is execution-detail blind

Core may orchestrate lifecycle, selection, evidence, directory allocation, and
scheduling. It must not import concrete adapter/source/capacity implementations
or execute project commands directly.

## AC-2: Project execution crosses only the execution boundary

Only project-owned execution integration may interpret project commands,
simulator output, board responses, or verification result rules.

The current public API is implemented by `ExecutionAdapter`, but the exact
Python method signatures are not an architecture invariant. The invariant is the
boundary: project execution semantics must not leak into core.

## AC-3: Job identity defines rerun granularity

A Job is an independently schedulable and independently rerunnable unit.

Required:

- unique within a plan;
- non-empty stable string identity;
- no leading/trailing whitespace;
- no control characters;
- JSON-serializable payload and metadata.

`--failed-from` selects failed **Job IDs**. Core does not split a Job into finer
project-defined tests.

## AC-4: Core allocates per-job ExecutionContext

Core creates isolated `work`, `artifacts`, and `logs` directories for every
selected Job and passes them to `execute`. Directory names are derived safely and
must not directly trust Job IDs as paths.

## AC-5: Large process output is file evidence

Adapter implementations must not place unbounded stdout/stderr bodies into
canonical JSON. File references and small metadata are the expected evidence.

The bundled process utility streams stdout/stderr directly to files and has no
`shell=True` API.

## AC-6: Process timeout is group-scoped

For subprocess-based adapters, the recommended utility starts a new process
session. Timeout termination targets the process group with SIGTERM followed by
SIGKILL after a grace period.

## AC-7: SCM semantics cross only SourceProvider

Core requests materialization but does not know Git/SVN commands. Built-in Git
and SVN are plugins, not core concepts.

## AC-8: Load semantics cross only CapacityProvider

Core knows only `available_slots()` and `max_parallel`. Queue/farm semantics
remain outside core.

## AC-9: Intent and machine evidence are separate

```text
regression.yaml   human intent
context.json      resolved/frozen context
plan.json         discovered canonical plan
run.json          selected/executed run evidence
result.json       canonical result evidence
```

## AC-10: FAIL rerun has explicit provenance

A FAIL-only rerun names the previous run/result explicitly. The new run records
the source result path, run ID, SHA-256, and selected Job IDs.

## AC-11: Integration must not require core modification

Normal project execution integration is declarative and does not require Python.
A project should first use the built-in command contract. External Python
plugins remain an escape hatch for execution/source/capacity behavior that
cannot be expressed by the small declarative boundary.

## AC-12: Connection checks are first-class

Every extension contract offers `probe`. `mockingbird doctor` orchestrates these probes
without materializing sources or running regression Jobs. Missing custom probe
logic may produce WARN; concrete connection failure produces FAIL.

## AC-13: Conformance is reusable

`mockingbird.testing` provides execution/source/capacity conformance helpers that can
be used from project-owned pytest suites. Contract changes require corresponding
conformance and documentation updates.

## Change rule

If a feature violates one of these rules, either redesign it or add an ADR that
explicitly replaces the rule and update architecture tests in the same commit.
Do not weaken a contract test merely to make a feature pass.

## AC-14: Simplicity is an architectural requirement

Core changes should introduce the minimum new knowledge and mechanism necessary.
Do not move system-specific policy into core for convenience, and do not create a
new abstraction solely for hypothetical future users.

Prefer the declarative contract and a project-owned wrapper first. Use a custom
adapter/provider only when the small boundary is genuinely insufficient, and
promote common mechanisms only after repeated real integrations prove them.

## AC-15: Project evidence remains opaque

Project-owned collection determines the result. Core must not infer PASS/FAIL
reasons from simulator logs, return codes, waveforms, traces, coverage databases,
board output, or other project-specific evidence.

Mockingbird may preserve associations/references so that a result can be traced
back to its Job, Execution, and project-owned evidence, but it must not require
heterogeneous artifacts to conform to a speculative common taxonomy.

A reason, artifact classification, or richer evidence schema is not mandatory
merely for uniformity. Promote such concepts only after repeated real
integrations demonstrate a stable common meaning.


## AC-16: The collected result envelope is deliberately small

The collector returns one outcome per requested executed Mockingbird Job.
An outcome is either an unresolved CollectionAttempt (PENDING/ERROR), or a final
TestResult. Core requires only these fields for a final result:

```text
id          Mockingbird Job ID
status      PASS | FAIL | ERROR | SKIP
artifacts   list[str]
```

Each collection call must match its requested Job IDs. Final results are a subset
of the selected set until collection completes; they then match that set exactly.

`artifacts` contains opaque references chosen by the collector. References are
not required to be filesystem paths. Core preserves them but does not classify,
resolve, open, validate, or interpret them. An empty artifact list is valid.

Other project-owned result information may be carried as optional opaque data,
but must not become mandatory without repeated real integrations demonstrating
a stable common need.


## AC-17: Normal execution integration is declarative

A user should normally integrate a runnable project by writing the execution
contract in regression.yaml, not by implementing Mockingbird Python code.

The normal boundary declares:

    per-Job command and argv
    finite local timeout
    Job identity
    per-Job result collection contract

Plan applies defaults then overwrites explicit Job fields, validates, and saves
complete contracts. A string Job uses its ID as argv unless defaults supplies
args. A mapping may override command, args, timeout, and the whole collect mapping.
Absent collect resolves to no-check. Execution never resolves defaults again. Python ExecutionAdapter
implementations remain supported only as an advanced escape hatch.

## AC-18: One permitted Job means one project command

For the declarative executor, one execute call starts exactly one project-owned
command for one permitted Mockingbird Job.

Mockingbird must not split that command into compile, submit, monitor, or other
project-specific phases. The project command may perform those operations
internally because that is the same boundary a human uses from a terminal.

The local command wait is finite. A finite positive timeout_s is therefore mandatory in every resolved Job. On return or timeout, Mockingbird releases its local
execution resources. Mockingbird does not create a resident daemon or detached
monitor to follow externally handed-off work.

## AC-19: Capacity is a hard dispatch gate

ADR 0009 restricts max_parallel to the integer 1, enforced in configuration
validation and at runtime before dispatch. Omission defaults to 1; other values
are errors, including in previously prepared contexts.

At every scheduling decision, new dispatch is limited by:

    allowed_running = min(max_parallel, available_slots())
    new_dispatch = max(0, allowed_running - locally_in_flight)

Mockingbird must not intentionally start another Job when new_dispatch is zero.

If reported capacity falls below the number already running, existing executions
are not killed. They may temporarily exceed the newly reported limit; new
dispatch remains stopped until capacity permits it again.

For asynchronous external hand-off, the CapacityProvider is responsible for
including already submitted external work in later capacity samples before more
Jobs are admitted. Core does not track external scheduler Job IDs.


## AC-20: Execution evidence and collection state are separate

Return codes and timeouts remain execution evidence. The declarative executor
never derives TestResult from them. no-check returns PASS without checking them.
Each returned execution is persisted before waiting for the entire run to finish.

## AC-21: Collection closes one immutable selected set

Contract, execution evidence, and result link by Job ID within one run. Repeated
collect visits only uncollected/PENDING/collection-error executions; it never
reruns execution or replaces a final result. PENDING and collection ERROR are
not final test judgements. Each outcome is checkpointed independently. A run is
not reported as PASS while any selected Job remains unresolved.

See ADR 0008 and Execution_Contract.md for the schema and external protocol.
