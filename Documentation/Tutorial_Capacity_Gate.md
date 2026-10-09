# Serial submission with limited external work

This runnable example demonstrates a different limit from local parallelism:
**submission commands run one at a time, but up to two submitted external Jobs
can remain unfinished**. A third Job waits until an external slot is released.
No simulator, licence server, background worker, or external queue is required.
The sample uses a file-backed queue and you manually mark external work complete.

Run commands from the Mockingbird clone after an editable installation. Use two
terminals, both in the same clone directory and with the same virtual environment.
Do not use `mb all` for this exercise: it would wait at the same capacity gate.

## Terminal A: prepare and start submission

```sh
mb prepare examples/capacity-gate.yaml
mb plan capacity-gate
mb run capacity-gate
```

No setup list is configured. The first two submission commands return immediately.
You should then see:

```text
[1/3] sim_a: command finished (exit=0)
[2/3] sim_b: command finished (exit=0)
[3/3] sim_c: waiting for capacity
```

**Leave terminal A running.** It is waiting deliberately, not hung. The capacity
command is checked every second. There is no automatic completion timer.

## Terminal B: inspect the external queue

```sh
python3 examples/sample_queue.py status
python3 examples/sample_queue.py slots
mb status capacity-gate
```

The queue reports 2/2 occupied slots; slots prints `0`. MB status shows two saved
execution records and sim_c waiting for capacity. The submit commands have
finished, while the simulated external work remains ACTIVE. ACTIVE includes both
queued and running work for capacity accounting.

While terminal A is still waiting, collect from terminal B:

```sh
mb collect capacity-gate
mb status capacity-gate --details
```

Expected: PENDING for sim_a and sim_b, UNCOLLECTED for sim_c. Collect exits with
code 2 because results are incomplete; it does not unblock submission or wait
for it to finish. No collector is called for sim_c yet. The same collect command
works both during and after run.

Copy the run ID shown by queue status (also visible in MB status):

```sh
RUN_ID=REPLACE_WITH_THE_DISPLAYED_RUN_ID
python3 examples/sample_queue.py finish "$RUN_ID" sim_a
```

This helper simulates external completion of sim_a. It changes only the project
queue record, not MB records. It is not a Mockingbird repair command.

Within the next poll, terminal A submits sim_c and returns. Queue status now shows
sim_a DONE, with sim_b and sim_c ACTIVE. Occupancy never exceeds two:

```sh
python3 examples/sample_queue.py status
```

The free slot may already have been used by sim_c when you inspect it. That is
expected. Run completion means all three submission commands returned, not that
all external work finished.

## Obtain final results

After terminal A returns, complete the remaining external work and collect:

```sh
python3 examples/sample_queue.py finish "$RUN_ID" sim_b sim_c
mb collect capacity-gate --run-dir "work/capacity-gate/runs/$RUN_ID"
mb status capacity-gate --run-dir "work/capacity-gate/runs/$RUN_ID"
```

Expected: three PASS results. The collector reads queue state; it does not use
the submit command's exit code as a verdict. If you collect before finishing
external work, those Jobs return PENDING and can be collected later.

## How the connection works

The definition's scheduler section is:

```yaml
scheduler:
  capacity_provider: command
  max_parallel: 1
  poll_interval_s: 1
  config:
    command: [python3, examples/sample_queue.py, slots]
    timeout_s: 10
```

| Component | Role |
| --- | --- |
| MB `max_parallel: 1` | Invoke local submission commands serially |
| `sample_queue.py submit` | Record an ACTIVE submission before returning |
| `sample_queue.py slots` | Print `max(0, 2 - active submissions)` as one integer |
| MB capacity polling | Wait while slots is zero; submit the next Job when positive |
| `sample_queue.py finish` | Simulate external completion and release occupied slots |
| `sample_queue.py collect` | Return JSON: ACTIVE -> PENDING, DONE -> PASS |

The limit of two lives in the sample queue's `LIMIT` constant, not in MB.
A real wrapper can instead query your queue or licence allocation. Count accepted
submissions immediately, including queued work. Polling alone is not an atomic
reservation: this sample also locks and enforces the limit during submission.
For multiple independent submitters, the external system/wrapper must enforce
that limit; increasing MB's local concurrency is not required for this workflow.

The capacity command is not given MB_RUN_ID/MB_JOB_ID by MB. This queue's capacity
is shared across its recorded runs; run and collect use their supplied identities.
During run, the capacity command uses the invocation directory saved by prepare,
just like execution and collection commands. Doctor uses the current invocation
directory for its preflight check. Relative workspace paths still resolve from
the current invocation, so use the clone directory throughout this tutorial.
Run, collect, and status can overlap. Do not prepare or setup the same plan
while run or collect is active; those preparation writes are protected by a lock.

## Files, interruption, and cleanup

- `work/capacity-gate/`: MB preparation metadata.
- `work/capacity-gate/runs/<run-id>/`: MB execution records, logs and collected results.
- `work/capacity-demo-queue/`: project queue state and lock, shared across runs.

Ctrl+C stops MB submission but does not complete or cancel external Jobs. In this
sample, previously submitted ACTIVE entries keep occupying slots, even for a new
run. Inspect queue status and finish those entries with their original run IDs.
An unsubmitted Job cannot be finished or collected successfully. Do not delete
queue state to recover real licences in an actual system.

After stopping MB and finishing the exercise, optional cleanup from the clone:

```sh
rm -rf -- work/capacity-gate runs/capacity-gate work/capacity-demo-queue
```

This deletes only this demo's MB workspace/history and simulated queue, including
any edits made there. Nothing is deleted automatically.
