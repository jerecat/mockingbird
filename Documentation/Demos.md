# Demos

## Direct Linux commands (serial)

```bash
mockingbird doctor examples/linux-commands.yaml
mockingbird all examples/linux-commands.yaml
```

Runs `pwd`, `ls -la`, `sleep 1`, `mkdir`, and `rmdir` directly in list order,
with `max_parallel: 1`. No project wrapper is needed. The next command starts
after the previous command returns and capacity permits it.

Defaults supply the timeout and empty arguments; each Job supplies its command
and any argument overrides. Plan resolves the omitted collector to `no-check`.
All commands run from the invocation directory. The temporary demo directory is
`work/linux-commands/demo-directory`; the final Job removes it when empty.

Expected: five execution records and five no-check PASS results. A no-check PASS
does not verify command success: inspect `executions.json` for return codes and
timeouts, and per-Job logs for output. The run files are under
`runs/linux-commands/<run-id>/`.

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
