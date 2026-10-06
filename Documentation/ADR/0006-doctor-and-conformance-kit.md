# ADR 0006: Doctor probes and reusable conformance tests

Status: Accepted

## Context

Most integration failures occur at the adapter/provider boundary: missing tools,
repository access, unstable job IDs, non-serializable payloads, bad result
cardinality, or scheduler-capacity contracts. Discovering these only after a full
regression starts makes adoption unnecessarily difficult.

## Decision

Three extension contracts expose a lightweight `probe` hook used by:

```bash
mockingbird doctor regression.yaml
```

`probe` is intentionally non-destructive and should check connection/prerequisite
health rather than run a regression.

The package also exports reusable test helpers:

```python
from mockingbird.testing import (
    check_execution_adapter,
    check_source_provider,
    check_capacity_provider,
    assert_conformance,
)
```

Project-owned pytest suites can use the same conformance logic before connecting
the adapter to nightly regression.

## Consequences

Connection checks become repeatable and automation-friendly. A project can fail
fast during integration while keeping project-specific knowledge outside core.
