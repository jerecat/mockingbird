# Named plans and execution history

Write a plan, confirm its contents, run it, and inspect the results. Edit and
confirm it again when needed. Keep the same plan name to continue its history;
choose another name to start a different plan.

```yaml
plan: smoke
sources: []
execution:
  defaults:
    command: [sh, ./run.sh]
    timeout_s: 600
    collect:
      command: [sh, ./collect.sh]
      timeout_s: 30
  jobs: [test_a, test_b]
scheduler:
  capacity_provider: fixed
```

## User operations

Start prepare from the project directory. It registers the plan's name and
original working directory. Named commands then work from any directory:

```sh
mb prepare regression.yaml
mb plan regression.yaml
mb dry-run smoke
mb run smoke
mb collect smoke
mb status smoke
mb status smoke --history
```

Use `mb setup smoke` after prepare when setup commands or a custom adapter hook
are configured. It is optional for standard command plans without setup Jobs.
`mb all regression.yaml` explicitly performs the complete sequence, including
one collection sweep. Repeating all also repeats preparation; use run to repeat
an already confirmed plan.

| Operation | Responsibility |
| --- | --- |
| `prepare YAML` | Acquire or reuse sources and record the prepared environment |
| `setup PLAN` | Execute the preparation commands saved by prepare |
| `plan YAML` | Resolve and validate execution settings, then confirm the complete plan |
| `dry-run PLAN` | Preview the confirmed Jobs and explicit selection |
| `run PLAN` | Execute the confirmed plan and save a copy in a new run |
| `collect PLAN` | Obtain unresolved results using the selected run's own plan |
| `status PLAN` | Read saved execution observations and results |

The `plan` key is required. Names contain 1-128 ASCII letters, digits, dots,
underscores or hyphens, starting with a letter or digit. Source `name` and Job
`id` keep their existing meanings.

A YAML filename is provenance, not identity. Two YAMLs with `plan: smoke` confirm
the same named plan in the user's registry, even from different directories. The last
successful confirmation supplies the next run. Editing, renaming or deleting
YAML after confirmation does not change execution or prevent result inspection.
Run does not reread YAML, compare edits, or offer to confirm implicitly.

```sh
mb plan a.yaml     # Contains plan: smoke
mb run smoke      # Executes a's confirmed contents
mb plan b.yaml     # Also contains plan: smoke
mb run smoke      # Executes b's confirmed contents
```

A failed confirmation returns an error and leaves the last successfully
confirmed plan intact. Plan does not run setup or acquire sources. Changes to
sources, setup or adapter preparation requirements need explicit prepare/setup
before confirmation. Execution and scheduler edits need only plan.

## MB chooses the storage paths

| Data | Location relative to the first prepare's project directory |
| --- | --- |
| All data for smoke | `work/smoke/` |
| Acquired sources | `work/smoke/sources/<source-name>/` |
| Preparation records and current plan | `work/smoke/.reg/` |
| Each execution and its results | `work/smoke/runs/<run-id>/` |

There are no YAML workspace or run-root settings. The first prepare registers
the name in `~/.local/state/mockingbird/plans/<plan>.json`, recording the absolute
project directory and original YAML path. Each name identifies one plan for this
user. Later prepare/plan/all with the same name use the original project, even
when the input YAML or the calling terminal is elsewhere. A new plan needs a
different name. MB looks up the registration; it does not search parent or nearby
directories or silently switch to a local copy.

`MB_STATE_DIR` can override the state directory; it must be absolute. Ordinary
use needs no environment setting. Tests and guided tutorials use isolated state
directories so their names cannot affect normal projects. This is single-user
plan management, not a shared-user registry or a results database.

For example, after preparing and confirming smoke under `/project`:

```sh
cd /tmp
mb run smoke
mb status smoke
mb collect smoke
mb status smoke --history
```

All four operations still use `/project/work/smoke/`. CLI arguments naming files
(YAML, --selection, --failed-from and --run-dir) are resolved from the caller's
directory as usual; use absolute paths when needed. They do not relocate plans.

An unknown name is an error, including `status --history`. A registered plan
with no runs reports `No runs yet.` for history. A missing registered location
reports its actual path instead of claiming that the plan has never run.

Commands and collectors use the invocation directory recorded at preparation
and included in the confirmed plan as cwd. The script's location does not imply
`cd`. Project scripts own their output paths; acquired sources and run logs do
not change the command cwd. Wrappers can change directory explicitly.

## Existing plans and cleanup

For a plan prepared before name registration was introduced, run
`mb plan /path/to/definition.yaml` once **from the original project directory**.
This registers the existing location and confirms the supplied YAML; it does
not repeat source acquisition or setup, move files, or alter older runs. It
requires the existing preparation to be usable. After that, use its name from
any directory. An explicit `--run-dir` still works without registration.

If two older project directories already contain the same plan name, registration
does not merge them. Prepare/plan/all from the conflicting local environment
report both locations. Continue with the registered project or use a new plan
name for the other project. Historical runs can still be read with --run-dir.

If files disappear, restore the registered location or explicitly prepare it
again. Prepare can recreate a removed `work/<plan>/` under the original project;
it does not recover deleted runs. If the project directory itself has gone, MB
reports the missing path and the registration file instead of choosing a new
location. To deliberately forget a name, stop active MB operations for it and
remove only its registration file, for example:

```sh
rm -- ~/.local/state/mockingbird/plans/smoke.json
```

Use the equivalent path under MB_STATE_DIR if overridden. This does not delete
the plan's source trees or run records. A subsequent explicit prepare can assign
the name to a new location. Existing absolute artifact paths are never rebased.

## Inspect results and the exact plan used

```sh
mb status smoke --history
mb status smoke --run <run-id>
mb status smoke --run <run-id> --details
mb status smoke --run <run-id> --plan
mb status smoke --plan
mb collect smoke --run <run-id>
```

`status --history` lists runs, newest first, with execution state, result state
and Job count. `status --plan` prints the complete confirmed plan as JSON; with
`--run`, it prints the plan saved by that run. `--json` is available for status,
history and collection. Results can be followed back to resolved Jobs, literal
argv, collector contracts, selection, cwd and preparation evidence.

Without a run selector, status and collect use the latest-started run. Finishing
an older run or collecting an older result does not change that choice. For
explicit directories, including legacy records, `--run-dir PATH` remains
available. It can also inspect another operator's compatible records without
registering or replacing that plan locally; the supplied name must match the
name in the saved run. A run with a different plan name is rejected.

Each collect replaces that run's result.json with the latest aggregate result.
Final Job verdicts stay fixed; unresolved Jobs can be collected again. Even a
collect of an already-final run regenerates the aggregate's generated_at. Use
started_at, not collection time, to order runs. The history command reads run.json
and result.json under this plan's runs directory, newest-started first; it does
not scan other operators' directories. Other result sets can be used by a
separate history consumer without changing plan registration. Historical plan
details remain in each run's adjacent plan.json, not embedded in result.json.

FAIL selection still requires an explicit previous result:

```sh
mb run smoke --failed-from work/smoke/runs/<previous-run>
```

This selects failed Job IDs from that result and executes their currently
confirmed contracts. It does not replay old contracts. The new run records both
the confirmed plan and selection provenance. Repeated collect retries unresolved
results within one run; it never reruns Jobs or replaces final results.

## What a confirmed plan contains

Schema 3 `plan.json` contains the plan name, confirmation time, original input
mapping, optional project `meta`, resolved Jobs, and the complete execution
context. The context includes cwd, scheduler/capacity configuration, adapter
configuration, setup contract/attempt, prepared source evidence, and MB/Python
version information. The run uses this saved context, not a mixture of current
YAML, current preparation settings and old Jobs.

`meta` is an optional JSON-compatible mapping for project provenance, such as
toolchain/build identifiers. It is retained without MB interpreting its meaning.
It does not automatically set seeds, choose executables or enforce versions:
put execution-affecting values in the actual command contract or wrapper inputs.

The same confirmed plan and explicit selection produce the same resolved Job
contracts. Each execution still has a new run ID and timestamps. Test outcomes,
capacity availability and external completion times can differ.

Source evidence is observed at prepare time. Scripts, tools, binaries, inherited
process environment and external systems remain project-managed. Exact rebuild
or replay requires the project to pin and retain those inputs. A mutable file
path alone does not identify its bytes. MB does not copy complete source trees,
capture inherited environment secrets, or claim byte-for-byte reproduction.

## Updating during execution

A run retains its own plan before dispatch. Confirming new contents while an
older run is active changes subsequent runs only. Confirmation publishes one
complete JSON file atomically; a failed write preserves the old file.

`run --interactive` confirms the exact displayed plan and selection; later
confirmation or selection-file edits affect subsequent runs only.

Multiple runs of one plan have separate records. Brief run-start locking makes
the latest-started pointer deterministic. Prepare/setup take an exclusive lock
against active planning, execution and collection; these operations otherwise
share the prepared environment. Locks are released when the MB process exits.
Status remains read-only. Two collectors for one run cannot run concurrently.

These locks cover MB processes, not external work after submission has returned
or edits by other tools. Project wrappers must isolate writable outputs by run
ID and coordinate shared source/build changes with external work. Job dispatch
inside each run remains serial, subject to the configured capacity gate.

## Migration from 0.5

1. Replace top-level `name` with `plan`; keep source names and Job IDs.
2. Remove `workspace` and `run_root`. MB now owns the layout above.
3. Run prepare, optional setup, and plan with the updated YAML.
4. Pass the plan name to setup, dry-run, run, collect and status.

Obsolete keys are rejected with migration guidance. Old files are neither moved
nor deleted automatically. Do not point a new configuration at old storage to
silently reinterpret it. Existing schema-2 execution records can still be read
or collected in place using the old top-level name as the plan selector:

```sh
mb status old-name --run-dir /absolute/path/to/old/run
mb collect old-name --run-dir /absolute/path/to/old/run
```

Their recorded scripts/artifact paths must still be available for collection.
New prepared contexts use schema 2 and `plan` instead of `name`; plan, run and result records
use schema 3. Per-run `plan.json` embeds the context, so new runs do not write a
second context.json copy. Legacy runs retain their original context.json.
The previous `last_result.json` pointer is no longer used or written.
