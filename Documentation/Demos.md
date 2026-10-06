# Demos

## Linux sanity

```bash
reg all examples/sanity-linux.yaml
```

Purpose: prove the lifecycle, scheduler, adapter boundary, and canonical result flow on an ordinary Linux machine without requiring a simulator or source repository.

## Explicit FAIL rerun

```bash
reg all examples/regression-fail-demo.yaml || true
reg run examples/regression-fail-demo.yaml --failed-from runs/<chosen-run>
reg collect examples/regression-fail-demo.yaml
```

Purpose: demonstrate that the FAIL source is selected explicitly rather than inferred as "latest".

## Self-hosted demo

```bash
reg all examples/self-host.yaml
```

Purpose: regorch schedules groups of its own pytest tests through a concrete `selftest` adapter. This demonstrates that the same core can orchestrate itself without acquiring pytest semantics.

## External adapter demo

```bash
pip install -e examples/external_adapter
reg all examples/external-adapter.yaml
```

Purpose: demonstrate project integration without editing the regorch package. The YAML points to `example_regorch_adapter.adapter:Adapter` using the external plugin form.
