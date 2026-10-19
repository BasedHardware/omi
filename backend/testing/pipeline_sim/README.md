# pipeline_sim: virtual-clock simulation of the batch sync pipeline

A deterministic, in-process discrete-event simulation. It drives the **real**
batch-pipeline state machine under production-shaped synthetic load, so
capacity and ordering problems show up in seconds locally or in CI instead of
during slow production ramps. It needs no cloud access, network, GPU, audio or
user data. Every identity is a synthetic `sim-owner-N`.

```bash
cd backend
python -m testing.pipeline_sim list
python -m testing.pipeline_sim run mixed_fleet_steady --seed 1
python -m testing.pipeline_sim run provider_exhaustion_window --json            # full gate sample
python -m testing.pipeline_sim run burst_owner_serial_sequencer --param per_owner_concurrency=32
python -m pytest tests/unit/test_pipeline_sim*.py
```

The exit code is the verdict code: 0 for `GATE_PASS`, 1 for `GATE_FAIL`, 2 for no work. The CLI runs
inside `testing.hermetic_network.block_outbound_network`.

## How it works

- **Virtual time** (`clock.py`). The simulation runs on asyncio's own event loop. The selector never
  blocks. It jumps the clock to the next timer, so `asyncio.sleep`, Pump heartbeats and polls cost no
  wall time. The run is seeded and single-threaded, so it is deterministic: a seed reproduces the same
  JSON byte for byte. Clock resolution is 1 ms because a float at epoch magnitude cannot represent the
  default 1 ns.
- **Store** (`store.py`). This is an indexed in-memory implementation of the batch `Store` protocol. It
  has the `FirestoreTransaction` semantics the real code relies on: buffered atomic writes, queries
  against committed state, and the `flush` privacy re-check on every `jobs`/`results` write. The privacy
  authority is the real `assert_batch_write_allowed`, run against `StrictFirestore` customer documents.
- **Scorer** (`scorer.py`). It builds a sample shaped like `fleet_gate.sh` from the job rows the gate
  would read, and polls it every 300 s like the gate's `POLL_SECONDS`. The verdict is the first failing
  poll, or else the end state. Thresholds are named constants that mirror
  `data/run-2026-10-13-two-lane-nemotron/ops/fleet_gate.sh`. That file lives in the workspace repo and
  is read for definitions only. The JSON keys match what the gate's `verdict()` consumes, so an external
  adapter can feed the sample to the real gate.

## Real modules vs models

| Real product code (imported unmodified) | Model (named, cited in code) |
|---|---|
| `database.batch_pipeline_intake.admit` | ASR fleet capacity, HPA, queue timeout, empty/failure/exhaustion (`stt.FakeSTT`) |
| `Scheduler` (DRR pull, leases, retry, quarantine, recover) | Paid fallback provider and paid-call counting (`stt.FakeModulate`) |
| `Pump.run`/`run_once` (pull, heartbeat, complete, fail, drain) | `admission.authorize` spend RPC (lease seal real; fair-use leaves allow; backfill 4 h/UID/day) |
| `PipelineWorker` (VAD windows, packing, padded retry, empty-ASR → `RecoveryWork`) | Cloud Tasks (named-task dedupe, hop latency, duplicate delivery) |
| `OrderedMerge`, `Serving.reconcile` | `recovery_candidates` query, `cancel_fenced_recovery`, `quarantine_fenced`, `purge_batch_owner` |
| `QuarantineRecovery.sweep/_dispatch/recover`, `RecoveryStore` | Projection and first summary (ordered per-owner cursor, executor cost) |
| `assert_batch_write_allowed` (privacy fence) | `sync_executor` and an isolated summary pool (`models.ExecutorModel`) |
| `chunk_identity`, `priority_for`, recovery dispositions | Legacy sync path and per-UID sequencer (`models.SequencerModel`) |
| | Cloud Run revision drain (`models.RevisionModel`) |

These module attributes are patched for the duration of a run and then restored: `pump.time`,
`pump.run_blocking`, `serving.time`, and three `quarantine_recovery` leaves. Environment flags come
from `sim.DEFAULT_FLAGS`. That is an explicit flag set *assumed* to be production-like and can be
overridden per scenario. Empty-ASR disposition stays off because it needs real WAV bytes.

The revision-drain model mirrors the `request_scoped`/`fire_and_forget` vocabulary of
`tests/unit/fixtures/revision_drain.py` from the unmerged `lane/opus-drain-harness` branch. That
fixture is absent here, so this is a minimal virtual-time equivalent.

## Scenarios

| Name | Phenomenon asserted by `tests/unit/test_pipeline_sim_scenarios.py` / `_revision.py` |
|---|---|
| `burst_owner_serial_sequencer` | 365-upload burst drains one job at a time per UID and fails the 15-min obligation; `per_owner_concurrency=32` clears it |
| `mixed_fleet_steady` | Healthy baseline passes every gate |
| `provider_exhaustion_window` | Empty ASR at HPA max causes `empty_asr` quarantines, then one paid recovery each; bounded recovery dispatch keeps the quarantine-to-projection p95 under 300 s, and the one terminal paid failure fails the gate as `unrecovered_quarantine` |
| `revision_replacement_mid_run` | Background first summaries are lost; request-scoped (`summary_dispatch='task'`) and lease-durable work survive |
| `stale_finalize_targets` | Merged targets complete, deleted targets are excluded, and no paid call lands after the fence; duplicates never double-spend |
| `privacy_blocked_users` | 409 at admission or purge mid-flight; no paid calls after the fence; reported under `sim.upload_status`/`excluded_uploads` |
| `summary_behind_transcription` | Shared `sync_executor` breaches the first-summary deadline; an isolated summary pool passes |

## Limits

- Models are deliberately small. Absolute numbers depend on the profiles, so compare runs with each
  other rather than with production dashboards. The phenomena, orderings and gate verdicts are what the
  tests pin.
- There is no Firestore contention, retry or partial commit, and there are no threads.
- Real projection (`Projector`), enrichment and LLM summaries are not run.
- Recovery provider latency is paid before the synchronous `recover()` call, so `running` has zero
  duration.

## Characterization goldens

`trace.py` turns one seeded run into a normalized trace of what a caller or operator could observe.
`tests/unit/test_pipeline_characterization.py` compares the trace of each configuration in
`trace.GOLDEN_CONFIGS` with `tests/unit/fixtures/pipeline_sim_goldens/<name>.json`. A refactor or rewrite
of the batch pipeline that preserves behavior leaves every golden unchanged.

The trace contains:

- **Per segment.** Each durable job transition (`state`, `recovery:<state>`, `client:<status>`) and
  each result-log transition, with the time bucketed relative to admission (`<1s` … `>=1h`). It also has
  every `/recover-quarantine` task-handler response, the paid-call count, the final job and result rows,
  and a summary of the committed result artifact (provider, outcome, evidence, word count and digest).
- **Per upload.** The intake outcome and its HTTP status (202 or 409), the dedupe target, and what the
  conversation shows: projected or excluded, speech seconds, word count and digest, and first-summary state.
- **Totals.** Paid calls and their outcomes, simulation counters, final job and recovery states, and the
  revision-drain counts.

The trace is built from store writes (`SimStore.observers`, purge deletes) and handler responses, never
from internal call order. Synthetic IDs are renamed by first appearance (`owner-1`, `seg-1`, `conv-1`).
Lease and intent tokens, URIs, owner hashes, queue links and absolute timestamps are dropped.

| Golden | Behavior pinned |
|---|---|
| `healthy` | Speech only: ready, leased, result_ready, committed, projected |
| `empty_asr_padded_retry` | An empty first ASR is rescued by the padded retry, or quarantines, spends one paid call, and recovers or settles as terminal empty |
| `empty_asr_terminal` | Every ASR attempt is empty: one paid call, then `no_recoverable_speech` |
| `provider_failure_quarantine` | Provider errors: five attempts with retries, then quarantine and one paid recovery |
| `privacy_fence_midflight` | 409 at admission; a mid-flight fence purges the owner, and no paid call lands after it |
| `deleted_merged_targets` | Merged targets project normally; deleted targets are purged, erased and excluded |
| `duplicate_delivery` | Duplicate upload (202, deduplicated), duplicate worker RPCs, duplicate recovery task (`held`) |
| `revision_replacement` | A background first summary is lost at replacement; durable work survives |

**Not covered.** The goldens pin the real state machine, which is admission, scheduler, pump, worker,
merge, serving and quarantine recovery. They do not pin the modelled parts. Projection, first summary,
the `content` status and Parakeet/Modulate behavior come from the simulation's models. So do Cloud Tasks
delivery, the `admission.authorize` RPC and executor timing. The legacy sync path is out of scope
entirely: `trace()` rejects `path='legacy'`. A change to a model or to `GOLDEN_CONFIGS` also changes the
goldens. That is a harness change, not a pipeline behavior change.

**Updating in a refactor PR.** Run the test. If it fails, the failure lists the changed JSON paths and
a bounded diff. A diff means observable behavior changed. If the change is intended, regenerate the
goldens and commit them in the same PR. Explain each changed path in the PR description:

```bash
cd backend
PIPELINE_GOLDEN_UPDATE=1 python -m pytest tests/unit/test_pipeline_characterization.py
git diff tests/unit/fixtures/pipeline_sim_goldens/
```

Some diffs are expected even when behavior is preserved. If a refactor merges two transactions, an
intermediate durable state disappears from the transitions, and other readers could have observed that
state. Review those diffs rather than normalizing them away.
