# Design Principles

Mockingbird is intentionally a **boring tool**.

Current scope does not permanently exclude advanced capabilities. See the
[future extensions note](.note/future_extensions.md) for the policy of preserving
simple defaults while allowing extensions justified by operational needs.

That is a feature.

The design follows a Unix-like preference for small tools with narrow
responsibilities, explicit boundaries, and behavior that can be understood
without knowing every system around them.

## Principle 1: Mockingbird does not understand the system it orchestrates

Mockingbird should know only what is necessary to orchestrate:

```text
Jobs exist
    |
capacity allows dispatch
    |
dispatch one Job
    |
receive execution evidence
    |
collect a canonical result
```

It should not know:

- simulator semantics;
- board/JTAG semantics;
- project command syntax;
- how many external scheduler jobs one command may create;
- Git/SVN implementation details;
- farm/queue policy;
- project-specific PASS/FAIL parsing.

Those belong outside the core.

## Principle 2: Keep the core small

The preferred architecture is:

```text
small core
+
small mandatory boundaries
+
project-owned implementation
```

A feature should not enter core merely because it may be useful.

Before adding knowledge or an abstraction, ask:

> Does Mockingbird itself need to know this?

If the answer is no, keep it in an adapter/provider/project wrapper.

## Principle 3: Prefer boring implementation

Simple code is easier to inspect, test, replace, and maintain.

Prefer:

- plain files over hidden state;
- explicit JSON/YAML evidence over implicit behavior;
- argv lists over shell command strings;
- small Python functions over framework machinery;
- wrapper commands over scheduler-specific logic in core;
- composition over deep inheritance;
- one obvious control path over clever orchestration.

The goal is not to make Mockingbird impressive internally.

The goal is to make it dependable and easy to maintain.

## Principle 4: Generalize only after real repetition

Do not add an abstraction because several future systems might need it.

First implement real adapters/providers. If the same mechanism repeatedly appears,
then consider extracting a common utility.

```text
real implementation
      |
real implementation
      |
same problem appears again
      |
consider common utility
```

Common code should be promoted from evidence, not prediction.

## Principle 5: Contracts protect meaning, not accidental API shape

Architecture contracts should protect semantic boundaries:

- core remains execution-detail blind;
- dispatch is gated by capacity policy;
- Job is the dispatch/rerun boundary;
- canonical evidence stays generic;
- project integration does not require core modification.

Exact Python argument names, method ordering, convenience helpers, and similar
v0.x API details are not architecture invariants.

Public APIs may evolve while the architectural meaning remains stable.

## Principle 6: Do not standardize what Mockingbird does not understand

Different projects produce fundamentally different execution evidence.

A simple command may leave only stdout, stderr, and a return code. A simulator
may leave logs, waveforms, traces, coverage databases, and other project-owned
artifacts. A board test may leave UART logs, dumps, or files with completely
different semantics.

Mockingbird must not invent a common artifact taxonomy merely to make these
systems look uniform.

The project-owned collector interprets project evidence and determines the
result. Mockingbird records the returned result and preserves enough association
to trace it back to its Job, Execution, and project-owned files/evidence where
available.

```text
project execution
      |
      +-- arbitrary logs / artifacts / observations
      |
project-owned collector
      |
      +-- interprets project-specific meaning
      |
      v
TestResult
      |
Mockingbird records and associates; it does not reinterpret
```

In particular:

- Mockingbird does not determine why a test passed or failed;
- a reason string is project-owned and may be absent;
- artifact names, formats, and semantics are project-owned;
- heterogeneous evidence should remain opaque rather than being forced into a
  speculative common schema;
- preserving traceability does not require understanding the evidence.

The minimal collected result envelope is intentionally small:

```text
Job ID + canonical status + opaque artifact references
```

Artifact references are strings. They will often be paths, but Mockingbird does
not care what namespace or format they use. It stores the references; the
project owns their meaning.

A useful rule is:

> **Do not standardize what Mockingbird does not understand.**

If repeated real integrations later reveal a genuinely common evidence concept,
it may be promoted deliberately.

## Principle 7: Maintenance cost is a first-class design constraint

Every abstraction, option, plugin hook, and dependency creates future work.

When two designs satisfy the same requirement, prefer the one with:

- fewer concepts;
- fewer branches;
- fewer hidden dependencies;
- fewer mandatory interfaces;
- easier failure diagnosis;
- easier deletion.

A useful Mockingbird feature should ideally feel unsurprising.

## Review rule

For every proposed feature, ask these questions in order:

```text
1. Does Mockingbird need to know this?
        no -> keep it outside core

2. Is this already a repeated real problem?
        no -> avoid premature abstraction

3. Can the same requirement be solved with a smaller interface?
        yes -> use the smaller interface

4. Will the next maintainer understand the failure boundary quickly?
        no -> simplify
```

This is the default decision rule for Mockingbird development.


## Principle 8: Declare integration before programming it

The normal project interface is regression.yaml plus project-owned commands.

A project that can already be operated from the command line should not need
Mockingbird Python code. Python plugins are an escape hatch for genuinely
different mechanisms, not the first integration step.

A useful rule is:

> A user integrates a project by declaring the contract, not by programming
> Mockingbird.

## Principle 9: Execute one command, then get out of the way

For a normal Job, Mockingbird should behave like a careful human at a terminal:

    capacity permits
          |
          v
    project command + argv
          |
          v
    wait within declared timeout
          |
          v
    command returns
          |
          v
    release local execution resources

Mockingbird does not turn compile, submission, monitoring, or simulator behavior
into another orchestration framework. If a project command hands work to an
external system, that external work remains project/system owned.


## Principle 10: Shorthand does not weaken the contract

Users can declare every field for every Job. Defaults reduce repetition, not
responsibility: plan resolves and validates a complete contract for each Job.
Execution evidence says what the executor did. The collector decides the result.
No-check deliberately performs no judgement; a pending collection has no final
result yet. All three remain associated by Job ID inside one run.
