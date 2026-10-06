# Getting Started

## 1. Create a development environment

From the repository root on a normal Linux machine:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

## 2. Run the architecture and unit tests

```bash
pytest
```

or:

```bash
make test
```

## 3. Run the zero-integration Linux sanity set

This uses only ordinary Linux commands behind the bundled demo adapter:

```bash
reg all examples/sanity-linux.yaml
```

or:

```bash
make sanity
```

Expected result:

```text
4 total / 4 pass
```

The core does not know that these jobs use `pwd`, `ls`, `mkdir`, or `rm`. That knowledge exists only in the demo adapter/configuration.

## 4. Inspect the evidence

After the run:

```text
work/.reg/context.json
work/.reg/plan.json
runs/<run-id>/context.json
runs/<run-id>/plan.json
runs/<run-id>/run.json
runs/<run-id>/executions.json
runs/<run-id>/result.json
```

`result.json` is the canonical input for future history/report/UI layers.

## 5. Exercise the lifecycle manually

```bash
reg prepare examples/sanity-linux.yaml
reg setup examples/sanity-linux.yaml
reg plan examples/sanity-linux.yaml
reg dry-run examples/sanity-linux.yaml
reg run examples/sanity-linux.yaml --interactive
reg collect examples/sanity-linux.yaml
```

## 6. Run regorch through regorch

The self-host demo connects the orchestrator to selected groups of its own pytest suite:

```bash
reg all examples/self-host.yaml
```

or:

```bash
make self-demo
```

This is useful as a small architectural demonstration: regorch itself becomes the DUT/test environment from the orchestrator's point of view, yet the core still sees only opaque jobs and canonical results.

## Next

For a real project, read `Documentation/Integration_Guide.md`. In most cases the only project-specific code is an external `ExecutionAdapter`; Git/SVN source acquisition and command-based capacity reporting can be reused as-is.
