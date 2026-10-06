# Demos

## Linux sanity

```bash
reg doctor examples/sanity-linux.yaml
reg all examples/sanity-linux.yaml
```

Purpose: prove connection probes, lifecycle, scheduler, per-job execution
contexts, streamed logs, and canonical result flow on an ordinary Linux machine.

## Explicit FAIL rerun

```bash
reg all examples/regression-fail-demo.yaml || true
reg run examples/regression-fail-demo.yaml --failed-from runs/<chosen-run>
reg collect examples/regression-fail-demo.yaml
```

Purpose: demonstrate explicit FAIL provenance and Job-granularity rerun.

## Self-hosted demo

```bash
reg doctor examples/self-host.yaml
reg all examples/self-host.yaml
```

Purpose: regorch schedules groups of its own pytest tests through the concrete
`selftest` adapter. Core still sees only Jobs and canonical execution/result
evidence.

## External adapter demo

```bash
pip install -e examples/external_adapter
reg doctor examples/external-adapter.yaml
reg all examples/external-adapter.yaml
```

Purpose: prove project integration, probe, process utility, and canonical result
collection without editing the `regorch` package.
