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
`pump.run_blocking`, `serving.time`, and three `quarantine_recovery` leaves. `SimConfig.policy` accepts
an immutable `BatchUnitPolicy`; otherwise admission resolves each owner from `DEFAULT_FLAGS` plus
`SimConfig.flags`, without installing scoped flags in the environment. The recorded policy follows
each upload. `SimConfig.policy_parts` supplies recorded stage parts for replay; otherwise each owner
resolves once from explicit flags at first handling. First-summary grading uses its obligation stamp. Only excluded worker dispositions
and process/provider settings retain isolated environment injection. Empty-ASR disposition stays off
because it needs real WAV bytes. Characterization uses the current recovery-dispatch default of 16
and leaves current main's existing golden files unchanged.

The revision-drain model mirrors the `request_scoped`/`fire_and_forget` vocabulary of
`tests/unit/fixtures/revision_drain.py` from the unmerged `lane/opus-drain-harness` branch. That
fixture is absent here, so this is a minimal virtual-time equivalent.

## Scenarios

| Name | Phenomenon asserted by `tests/unit/test_pipeline_sim_scenarios.py` / `_revision.py` |
|---|---|
| `burst_owner_serial_sequencer` | 365-upload burst drains one job at a time per UID and fails the 15-min obligation; `per_owner_concurrency=32` clears it |
| `mixed_fleet_steady` | Healthy baseline passes every gate |
| `provider_exhaustion_window` | Empty ASR at HPA max causes `empty_asr` quarantines and one paid recovery each; shipping bounded dispatch clears the 300 s tail, while a labeled former-rate counterfactual reproduces it. Unrecovered audio still fails the gate |
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

## Owner-chain projection throughput (`projection-drain`)

```bash
python -m testing.pipeline_sim projection-drain --rows 1200            # one heavy owner, every mode
python -m testing.pipeline_sim projection-drain --rows 300 --owners 12 # many heavy owners, one instance
```

Unlike the scenarios above, `projection_drain.py` runs the **real** `Projector`
walk, sweep and `OwnerDrains` scheduler. The modelled parts are the result log,
the owner claim, sync assignment (sessions of contiguous rows, with bridges
that absorb a donor) and the Typesense index. Every store, GCS, Typesense and
transaction call charges a fixed run-14 p50 latency (`LATENCY`) to the lane
that made it. A read-ahead or parallel lookup is its own lane, so overlap is
modelled. Firestore hot-document contention and retries are not. Modes:
`sweep_walk` (today), `drain_only` (scheduling only) and `drain` (Phase 1). It
reports rows/min per owner, pre-check transactions and result loads. The
assignment calls (candidate hints and new donors included) and the final index
must match `sweep_walk` exactly. `tests/unit/test_pipeline_sim_projection_drain.py`
pins this; its 1.2k-row and many-owner cases are marked `slow`.

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


E1's `role_policy` case uses separate sync and integration environments through
`SimConfig.role_environments` and `stage_roles`. Its trace opts into policy values,
source roles and stable hashes; changing either projection or recovery to the
sync role must break the golden. Historical goldens keep their existing trace
format. Projection's model uses the real stage-part CAS before projecting.
### Bounded recovery dispatch golden review (#22321)

The shipping default dispatches up to 16 candidates per pass, including held or
error rows, instead of stopping after the first dispatched recovery. The three
updated traces describe that default, without a legacy-rate flag override:

- `empty_asr_terminal`: preparation/recovery/completion buckets move earlier and
  result arrival changes `log_sequence`, `previous_segment_id` and `late_capture`.
- `provider_failure_quarantine`: only those result-log arrival fields change.
- `privacy_fence_midflight`: earlier preparation also changes queued task/held
  responses and request completion/horizon counts. Model task enqueues rise from
  18 to 27 and held responses from 4 to 8; those are not additional paid calls.

Reviewed paired traces retain identical upload projections/exclusions, content,
result artifacts (including word digests), paid outcomes and paid calls: 5, 6 and
7 respectively. Every segment still pays at most once, and each surviving
owner's result sequence is contiguous with an unbroken predecessor chain.
Privacy-fenced jobs remain purged; the scenario assertions still reject paid
calls after the privacy fence. Golden trace normalization and golden scenario
configurations are unchanged. These are scheduling observations of the existing main change,
not a change to transcript, payment or privacy expectations.

The exhaustion scenario also keeps its shipping-default baseline: dispatch batch
16 reduces quarantine-to-projection p95 to 89.7 seconds for seed 1, versus 1512.5
seconds in the explicitly labeled former-rate counterfactual. Both spend 132
modeled paid calls (at most one per segment), recover 131 pieces and retain one
`failed_held` piece. The shipping baseline therefore still reports
`GATE_FAIL unrecovered_quarantine`; clearing the scheduling tail does not turn
unrecovered audio into a successful gate. No shipping flag is pinned to the old
rate to preserve a stale expectation.

### Generated policy sweep (E3)

`tests/unit/test_pipeline_sim_policy_invariants.py` runs a fixed-seed pairwise
slice with injected `BatchUnitPolicy` and `ListenSessionPolicy` objects. The
suite checks the durable per-owner result chain, no duplicate paid calls,
privacy/deletion and stale-target fences, recorded-policy equality, and listen
arm stability across reconnect. It also seeds a double vendor charge and
asserts the invariant rejects it. The E1 `policy_window` golden is replayed
from its recorded policy ID and stage inputs.

Run all pairwise rows with `python scripts/policy_pairwise_sweep.py --seed 1`.
The script prints array size, feasible and covered pair counts, simulated rows,
and elapsed time. Nightly scheduling is pending David; no workflow is added.
