# Adapter Conformance Testing

Integration should be testable independently of a nightly regression.

## Layer 1: `reg doctor`

```bash
reg doctor regression.yaml
```

`doctor` is non-destructive. It validates configuration, loads all plugins, and
calls their `probe()` hooks.

Typical output:

```text
PASS  configuration            definition           definition is structurally valid
PASS  source:dut               plugin               git
PASS  source:dut               git                  git version ...
PASS  source:dut               repository           repository reachable without interactive prompt
PASS  execution                plugin               my_project.adapter:Adapter
PASS  execution                simulator            VCS executable/license reachable
PASS  capacity                 command              capacity command returned 6
```

Any `FAIL` gives a non-zero command exit status. `WARN` is informational and does
not fail doctor.

Probe rules:

- cheap and non-destructive;
- no full regression;
- no interactive credential prompt;
- do not print secrets into `CheckResult.message/details`.

## Layer 2: project-side pytest conformance

A project-owned adapter package should include tests similar to:

```python
from regorch.testing import assert_conformance, check_execution_adapter


def test_regorch_adapter_contract(tmp_path, project_context):
    checks = check_execution_adapter(
        MyAdapter(),
        project_context,
        tmp_path,
        exercise_execute=True,
    )
    assert_conformance(checks)
```

The execution helper verifies:

- probe is callable;
- `setup()` can be called twice;
- plan IDs are unique;
- two plans under the same context have stable ID/order;
- Jobs are JSON serializable;
- sample `execute()` returns the same Job ID;
- `JobExecution` is JSON serializable;
- sample `collect()` returns one matching canonical result.

`exercise_execute=False` may be used for a fast structural test when the real
system is not available in ordinary unit-test environments.

## SourceProvider conformance

```python
checks = check_source_provider(
    provider,
    source_definition,
    tmp_path / "materialized",
)
assert_conformance(checks)
```

This verifies probe behavior, materialization evidence, `resolved_revision`, and
JSON serializability.

## CapacityProvider conformance

```python
checks = check_capacity_provider(provider)
assert_conformance(checks)
```

This samples capacity more than once and verifies a non-negative integer result.

## Why both layers?

`doctor` answers "can I connect from this machine now?". The conformance test kit
answers "does my implementation obey the integration contract?". Both are needed:
one is runtime/environment health; the other is adapter architecture/API health.
