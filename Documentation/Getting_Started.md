# Getting Started

## 1. Install for development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

The package installs both the full command and a short alias:

```bash
mockingbird --help
mb --help
```

Both are registered in `pyproject.toml` and invoke the same CLI entry point.

## 2. Run repository tests

```bash
pytest
```

or:

```bash
make test
```

## 3. Check connections before doing work

```bash
mockingbird doctor examples/sanity-linux.yaml
```

`doctor` is non-destructive: it validates configuration, plugin loading,
configured Linux commands, and capacity-provider health without preparing a
frozen context or starting Jobs.

## 4. Run zero-integration Linux sanity

```bash
mockingbird all examples/sanity-linux.yaml
```

or:

```bash
make sanity
```

Expected result is four PASS Jobs. The example uses a declarative execution
contract and `examples/sanity-run.sh`; core does not understand the commands
inside that project-owned wrapper.

## 5. Inspect evidence

```text
work/.reg/context.json
work/.reg/plan.json
runs/<run-id>/context.json
runs/<run-id>/plan.json
runs/<run-id>/run.json
runs/<run-id>/executions.json
runs/<run-id>/result.json
runs/<run-id>/jobs/<job>/
  work/
  artifacts/
  logs/stdout.log
  logs/stderr.log
```

## 6. Exercise lifecycle manually

```bash
mockingbird doctor examples/sanity-linux.yaml
mockingbird prepare examples/sanity-linux.yaml
mockingbird setup examples/sanity-linux.yaml
mockingbird plan examples/sanity-linux.yaml
mockingbird dry-run examples/sanity-linux.yaml
mockingbird run examples/sanity-linux.yaml --interactive
mockingbird collect examples/sanity-linux.yaml
```

## 7. Run mockingbird through itself

```bash
mockingbird all examples/self-host.yaml
```

or:

```bash
make self-demo
```

## 8. Integrate a real project

Start with the declarative contract. No project Python is required:

    execution:
      command: ["./run.sh"]
      timeout_s: 600
      jobs:
        - test_a
        - test_b
      collect:
        mode: exit-code

For a submit-and-return flow, replace exit-code collection with one shared
project collector command.

Read `Execution_Contract.md` first, then `Integration_Guide.md`.

Only read the adapter implementation/conformance guides when the declarative
boundary is genuinely insufficient and a custom Python adapter is needed.
