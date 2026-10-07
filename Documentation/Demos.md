# Demos

## Linux sanity

```bash
mockingbird doctor examples/sanity-linux.yaml
mockingbird all examples/sanity-linux.yaml
```

Purpose: prove the no-project-Python declarative command path, connection probes,
lifecycle, capacity gating, per-job execution contexts, streamed logs, and
canonical result flow on an ordinary Linux machine.

## Explicit FAIL rerun

```bash
mockingbird all examples/regression-fail-demo.yaml || true
mockingbird run examples/regression-fail-demo.yaml --failed-from runs/<chosen-run>
mockingbird collect examples/regression-fail-demo.yaml
```

Purpose: demonstrate explicit FAIL provenance and Job-granularity rerun.

## Self-hosted demo

```bash
mockingbird doctor examples/self-host.yaml
mockingbird all examples/self-host.yaml
```

Purpose: mockingbird schedules groups of its own pytest tests through the concrete
`selftest` adapter. Core still sees only Jobs and canonical execution/result
evidence.

## External adapter demo (advanced escape hatch)

```bash
pip install -e examples/external_adapter
mockingbird doctor examples/external-adapter.yaml
mockingbird all examples/external-adapter.yaml
```

Purpose: prove project integration, probe, process utility, and canonical result
collection without editing the `mockingbird` package.


## Virtual operations rehearsal

Run the actual CLI against an isolated simulated external service:

```sh
python -m pytest -q -s tests/test_virtual_operations.py
```

This covers pending/error recovery, immutable completed results, capacity gating,
and a failed-only rerun. See `Virtual_Operations.md` for the observed cycle table.
