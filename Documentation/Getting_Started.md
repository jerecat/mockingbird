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

For a guided first experience, run `mb tutorial`. It explains and executes the
normal lifecycle in a new directory and finishes with optional cleanup guidance.
See [Guided tutorial](Guided_Tutorial.md). The remaining sections are also useful
as a manual reference.

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

```sh
mb status linux-sanity --history
mb status linux-sanity --run <run-id>
mb status linux-sanity --run <run-id> --plan
```

Records live under `work/linux-sanity/runs/<run-id>/`: plan.json, run.json,
executions.json, collection.json, result.json and per-Job logs/checkpoints.
The plan contains the full saved context. Original YAML is not required for
inspection or collection.

These named commands work from any directory after prepare registers the plan.
The paths above remain relative to the original project directory. Without
--run, status shows the latest-started run; an uncollected latest run is shown as
uncollected instead of falling back to an older result.

## 6. Exercise lifecycle manually

```bash
mockingbird doctor examples/sanity-linux.yaml
mockingbird prepare examples/sanity-linux.yaml
mockingbird plan sanity-linux
mockingbird dry-run linux-sanity
mockingbird run linux-sanity --interactive
mockingbird collect linux-sanity
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
        mode: no-check

no-check does not verify command success. For checked results, supply a project
collector command in defaults or per Job. Repeated collect visits only unresolved
Jobs; it does not execute them again.

Start with [From shell commands to Mockingbird](From_Shell_to_Mockingbird.md).
It connects one familiar shell command to a Job, then adds collection and defaults.
Use [Execution Contract](Execution_Contract.md) as the field reference and
[Integration Guide](Integration_Guide.md) for capacity and asynchronous systems.

Only read the adapter implementation/conformance guides when the declarative
boundary is genuinely insufficient and a custom Python adapter is needed.


For project preparation commands and failed-setup retries, see [Setup Contract](Setup_Contract.md).
Setup is optional for command definitions with no setup list.
