# Batch record lane contract

Status: ratified promises as of 2026-10-25 (ramp at 5%, PERCENT=0 after the
10:39Z T2 rollback). Review by 2026-11-01 or at the 100% step, whichever is
first. Rulings behind each promise are in [`docs/adr/`](../../docs/adr/README.md);
a promise with no ADR is not durable ([ADR 0005](../../docs/adr/0005-rulings-live-in-adrs.md)).
Package map: [README.md](README.md). Design: [batch-pipeline-worker.md](../../docs/batch-pipeline-worker.md).

The record lane turns an accepted upload into the conversation's transcript of
record. Live transcription is a preview; the batch result is the record.

## Promises

| Promise | What is guaranteed | Enforced by (code) | Trip |
| --- | --- | --- | --- |
| **Custody** | An accepted input object is never lost. Original bytes are archived before any 202 (`routers/sync.py:sync_local_files_v2`); every source reference is owner/conversation scoped and pinned to one GCS generation (`source_audio.py:validate_reference`, `read_reference` reads with `if_generation_match`). An ambiguous admission reply keeps the staging outbox and returns 503 (`intake.py:accept_upload`); it never releases a legacy twin. A quarantined unit keeps its encrypted artifacts with no TTL until recovery (`retry_policy.py:quarantine_job`). | `intake.py`, `source_audio.py`, `artifacts.py`, `retention.py` | T1, T2 |
| **Latency** | Soft bound, not a hard SLA ([ADR 0001](../../docs/adr/0001-trip-floors-t2-t3-t5.md)): an obligation over 900s or a job over 1,800s is a freeze through 50%. Hard backstops roll back: record latency p95 over 30 min for 30 min; any admitted unit 2h without a terminal state; wedged units over 5% of admitted for 30 min (at least 20 admitted). Audio waits in custody; latency trouble is never loss. | `scheduler.py:Scheduler` (120s token-fenced leases, `owns_lease`), `merge.py:OrderedMerge`, `pump.py` | T3 |
| **Transcript route** | No unit in an unsupported language is decoded on Parakeet; every completed unit carries route proof. | `utils/stt/batch_language.py:resolve_language`, `select_decision`; route receipts via `language_metrics.py:record_route` (intake, `diarizer/batch_pipeline.py` worker) | T4 |
| **Speaker naming** | Through 5–25%: #23581 links/names retained-audio batch groups. David approved temporary sync-off centroids in [ADR 0004](../../docs/adr/0004-sync-off-speaker-centroids.md) at ~14:45Z on 2026-10-25; delivery is the separately reviewed qualfix2 PR. Product owner ruling 2026-10-25 ~09:40Z (option A): keep ramping and fix naming in parallel, so naming quality is **not** a trip. FP32 flight batching needs a one-time speakers-per-unit parity check (±5%). | `projection.py:Projector`, `utils/conversations/speaker_resolution.py` | none (watch) |

## Inputs and outputs

- **Job document** (`database/batch_pipeline_*.py`, shape in `contracts.py:WorkItem`):
  immutable `segment_id`, `owner_id`, `capture_at`, `duration_seconds` (0–7,200s),
  `priority`, `unit_kind` (`conversation` | `capture_span`), `conversation_id`,
  `privacy_generation`, encrypted `audio_uri`. Mutable: attempt, lease token and
  deadline, retry time, `result_uri`, merge status, `state`
  (`quarantined` with `recovery_state` `held` → `prepared` → `running` → terminal
  recovery outcome `failed_held`, or `recovered` with `state=result_ready`;
  eligible dormant GPU holds can become retained `dead` rows as specified below).
  No transcript or audio bodies in queue metadata.
- **Admission**: one transaction binds the content ledger `dispatch_protocol=batch_v1`,
  the sibling set, the frozen projection binding and `intakes/bp_<job>` status.
  Policy is frozen per unit at admission (`config/policy/batch.py`).
- **Result**: `contracts.py:WorkResult` (`segment_id`, encrypted `result_uri`,
  `outcome` from `WORK_OUTCOMES`); holds are `HeldWork`, recovery handoffs `RecoveryWork`.
- **Projection**: `projection.py:Projector` follows the capture-ordered log from
  `merge.py:OrderedMerge`; late captures keep their clock and append after the
  committed tail. Per-part receipts in `projection_parts.py`; only complete
  multipart projection advances the owner cursor. A chain head nothing can
  resolve takes the held disposition instead of wedging every later capture:
  structural record-target conflicts (strike rule,
  `utils/sync/assignment_errors.py`), ambiguous generation, and committed
  payloads that violate the result/manifest contract (`ValueError` from spans,
  split, word bounding or source decode; Firestore contention-shaped
  `ValueError` stays retryable). Fresh awaiting-writer conflicts keep waiting
  for their writer; `tests/unit/test_pipeline_sim_poison_head.py` pins every
  kind, and `tests/unit/test_batch_projection_exception_taxonomy.py` fails
  when a new raise site appears without a disposition.
- **Contention**: `database/batch_pipeline_store.py:FirestoreStore.run` retries
  fresh Firestore transaction IDs on explicit `Aborted` contention and expired
  transaction errors (up to five chains; expired chains keep the three-chain
  ceiling). The worker's pull loop applies a jittered 0.5–30s cooldown after
  exhaustion. `BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false` restores the old
  transaction behavior. Other `InvalidArgument` and application errors are not
  retried or quarantined as poison without unit-specific evidence.
  Pullers take a token-fenced, 30s `pull_claims/scheduler_NN` lease with a
  single compare-and-swap (create or update-time precondition), without
  a claim transaction/retry loop, before
  touching control/queue/job metadata. The pull transaction verifies that
  token and releases it atomically; an error leaves a bounded claim for
  expiry/takeover. Followers only read hints or the claim, never write control.
  Equal-service candidates use worker affinity; service remains the primary
  fairness key, and busy higher-priority work prevents backfill bypass.
  `BATCH_SHARD_SPREAD_ENABLED=false` restores legacy pulls (Helm:
  `worker.shardSpreadEnabled=false`). Retry logs include only static
  `operation=batch_claim|batch_pull shard=scheduler_NN`, never worker/user IDs.
  One claimed shard transaction leases up to the pull's remaining batch,
  continuing the same DRR walk (each new head re-checks privacy, policy and
  pool; `MAX_VISITS` still bounds the whole walk, which also stops at 300
  buffered writes and commits its rotations for the next pull without a shard
  backoff; one token per lease).
  `BATCH_PULL_MULTI_LEASE_ENABLED=false` restores one lease per transaction
  (Helm: `worker.pullMultiLeaseEnabled=false`).
  Owner (re)activation seeds a rejoining shard's service from the frontier read
  OUTSIDE the admission transaction (`FIRESTORE_READ_LEVERS`
  `admission_frontier_hint`, default on; 0 restores the transactional query).
  The transactional query locked the top control doc and made admissions exhaust
  their retries (sync 503 storm, 2026-11-07). Trade-off: a pull that commits
  during the admission transaction can leave the joiner below the true frontier,
  so activation stamps `p{prio}_frontier_hint` and the store re-seeds the shard
  right after the admission commits (`reseed_hinted_activation`: a fresh
  non-transactional frontier read, then a lift on the shard's own control doc only
  while the marker is set; one attempt, 1.5 s RPC deadlines, failures only
  logged). The marker is the activation time: a pull that beats the re-seed
  within 30 s lifts the shard itself from a fresh frontier read; a later pull only
  consumes it (`consume_frontier_hint`), so waiting its turn is never charged to
  the joiner. Residual gap: pulls committed between the admission commit and that
  read (milliseconds). Earned credit is never lowered (`max(own, frontier)`).
  A pull stops at a claimed fresh shard only on a pump's first lane. Its other
  lanes, finding every eligible fresh shard claimed, lease recent/deep backfill
  instead of returning empty: the claimant is serving that fresh work, and the
  first lane keeps fresh-first per pump. A shared live GPU never borrows.
  `BATCH_PULL_BUSY_BORROW_ENABLED=false` restores strict fresh-first on every lane
  (Helm: `worker.pullBusyBorrowEnabled=false`).
  The existing Sync Cloud Tasks batch emulator gate runs the three-puller
  concurrency regression after its process-level batch scenarios.
- **Receipts**: durable upload status via `intake.py:durable_status`
  (`failed` + `failed_segments` + `batch_worker_quarantined` only for terminal
  quarantine); VAD/silence evidence in the result payload (`contracts.py:projection_speech_spans`);
  `omi_batch_pipeline_events_total` counts are best effort, the job records are the census.

Held partial uploads return nonterminal `processing/batch_unit_held`, with a
five-minute poll hint. Projected conversations stay visible independently of
upload completion, including after 30 minutes. Only all-unit completion can
acknowledge the phone's custody WAL; a partial ledger never authorizes that
acknowledgement or phone-local age eviction. Polling does not retry audio or
consume the client's failure budget. Pending phone bytes remain until recovery
or explicit user deletion; storage pressure cannot evict them.
`tests/unit/test_batch_pipeline_custody_property.py` checks this over every unit
state and ledger shape and pins each answer in `tests/fixtures/custody_status_shapes.json`,
which the phone replays through its terminal policy (`app/test/unit/custody_status_shapes_test.dart`).

Owner drains with zero progress waiting on `live_target_not_persisted` are held
out of admission for 30, 60, 120, 240, then at most 300 seconds per owner. The
hold is passive: its expiry only re-admits the owner for the next ordinary
request (the sweep) and never wakes it, so retries are never more frequent than
the sweep (an active wake doubled owner-chain conflicts on 2026-11-09). The hold is
passive only while this process runs a recurring sweep (the serving loop with
`BATCH_PIPELINE_SERVING_PROJECTION_SWEEP` on, or the projection pump), signalled by
the runtime itself; otherwise (serving off, sweep off, one-off reconcile requests)
it keeps its expiry and overflow wake, so no owner is stranded. Known pre-existing edge (lead2 8567be): with no serving runtime, a `defer()` overflow past `MAX_DELAYED_OWNERS` only queues `request_drain`, which nothing consumes until the next reconcile; it needs serving off plus a manual reconcile burst over 1,024 owners. Counted by
`omi_batch_projection_live_target_backoffs_total`; progress or any other stop
resets the bounded process-local attempt state. Only
`PROJECTION_DRAIN_LIVE_TARGET_BACKOFF=off` disables this backoff (restoring
`head_error`); privacy/deleted dispositions, other writer waits, productive FIFO
continuations and the durable 24-hour hold bound remain unchanged.

## Trips: which invariant each enforces

Registry: omi-workspace `infra/rollout/trips.toml` (rollback authority only with a
passing backtest receipt). All are cohort-scoped: only units the change admitted.

| Trip | Invariant | Authority |
| --- | --- | --- |
| T1 custody missing/mismatch | Custody: object present, right size and generation | rollback, no floor |
| T2 lost speech | Custody: no measured unrecovered speech (unit ≥120s, or >0.2% over ≥3,600 speech-s). Unknown VAD is not measured loss ([ADR 0002](../../docs/adr/0002-unknown-vad-freezes.md)) | rollback |
| T3 wedge + backstops | Latency (above) | freeze ≤50%, backstops roll back |
| T4 route | Transcript route | rollback, no floor |
| T5 failed_held | Recovery stays bounded: >2% with terminal ≥50 and failed_held ≥2 | rollback; below floor freeze |
| T6 intake 5xx | Admission services are healthy. UNVERIFIED as a trip: not in `trips.toml`; the 10-25 observer emits it as a BLIND/alert for lead attribution | alert |

A missing or stale read freezes expansion; it never rolls back.

## Held / dead-letter state table

**Owner: uicleanup (omi-lifecycle).** Ruling lead2 `2f9297`, daily-review
PA-1106-01, makes this the projection/held contract before phase 4c, phase 2,
or phase 5. Only this owner may add or change a projection/held or dead-letter
shape, through a PR that touches this section. Other lanes must route changes
through this owner. This inventory describes source behavior, not deployment
or live alert delivery. Machine/state keys match
`backend/tests/support/lifecycle_state_table.py`; they are not interchangeable.

Paths below are relative to `backend/`. Writer aliases expand to these files;
each table entry names the function after the alias:

- J = `utils/batch_pipeline/scheduler.py`; Q = `utils/batch_pipeline/retry_policy.py`;
  R = `database/batch_pipeline_quarantine_recovery.py`;
  M = `utils/batch_pipeline/merge.py`; V = `utils/batch_pipeline/provider_stt.py`.
- P = `database/batch_pipeline_projection.py`;
  S = `database/batch_pipeline_projection_session.py`;
  U = `database/batch_pipeline_projection_release.py`;
  H = `utils/batch_pipeline/held_dead_letter.py`.
- F = `database/conversation_finalization_jobs.py`;
  C = `utils/conversations/lifecycle.py`; A = `database/record_audio.py`.

`none` means no such current mechanism, not an exemption from future work.
Terminal rows have no normal automatic exit. Re-drive is a fenced recovery,
never proof of transcript publication. Phase 2a persists backend-only
`terminal_family=success` and `terminal_family_at` through
`database/conversations.py:claim_conversation_status_in_txn` for the status-claim
wrapper and processor persist, under `CONVERSATION_TERMINAL_FAMILY_MODE` (on by
default). Processor content and status commit together; a stored failure family
or `finalization_status=dead_letter` refuses success while still merging content.
Unclassified `failed` rows also refuse completion. Only explicit user restoration
supersedes failure markers and clears the old dead-letter marker with success;
retry-trigger provenance alone never grants restore authority. Non-completed
processor payloads merge content without regressing a stored completed status.
Committed refusals count `omi_conversation_terminal_claim_refusals_total{family,reason}`
with distinct `terminal_failure` and `completed_status_regression` reasons.
Legacy rows may lack the classifier. Other writer-family routing remains
**PLANNED phase 2b**; no API model, receipt, backfill, custody or drain change.
Off restores legacy writes and leaves classifier fields inert.

### Batch job

T = `omi_batch_timeliness_new_oldest_age_seconds` with
`omi-batch-unit-unpublished-2h` (page). These are recent-cohort publication-age
backstops, not dedicated dwell gauges for each state. B = existing serving
maintenance (`utils/batch_pipeline/serving.py:start_serving_from_env.run`).

| Machine:state | Entry writer | Exit writer | Deadline field | Dwell metric | Alert | Flag / kill switch | Rollback behavior |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `batch:record_pending` | `utils/batch_pipeline/live.py:register_recording` | Normal record admission; `utils/batch_pipeline/live.py:drain_recordings` defer CAS → retained `dead` for aged barrier refusal | `record_dead_letter_deadline_at`, stamped on first literal barrier failure; 14 days, including old rows | `omi_batch_record_dead_letter_total`, `omi_batch_record_dead_letter_units`, `omi_batch_record_dead_letter_observed_at_seconds`; existing pending dwell | `omi-batch-record-dead-letter-volume` (agent); existing pending dwell page | `BATCH_HELD_DEAD_LETTER_ENABLED` (true) | False preserves ordinary defer; no custody/audio/conversation writes; private OIDC requeue-record |
| `batch:ready` | `J:Scheduler.enqueue_in_transaction`, `J:Scheduler.requeue_quarantined_in_transaction` | `J:Scheduler._pull_shard.commit` | none | T | T | No held-specific switch | Existing queue/ownership fences |
| `batch:leased` | `J:Scheduler._pull_shard.commit` | `J:Scheduler.complete`, `J:Scheduler.recover` | `lease_until` | T | T | No held-specific switch | Token-fenced lease expiry |
| `batch:retry` | `utils/batch_pipeline/scheduler.py:_defer`, `J:Scheduler.defer` | `J:Scheduler.recover`, then `J:Scheduler._pull_shard.commit` | `available_at` retry schedule; no total dwell deadline | T | T | No held-specific switch | Retain attempts and custody |
| `batch:result_ready` | `J:Scheduler.complete`, `R:RecoveryStore.settle`, `V:ProviderSttStore.settle` | `M:OrderedMerge.commit_next` | none | T | T | No held-specific switch | Retain result, ordered merge |
| `batch:vendor_held` | `V:ProviderSttStore.hold` | `V:ProviderSttStore.redrive` via `V:ProviderSttStage._held` | `vendor_hold.redrive_at` retry schedule | T; `omi_batch_pipeline_vendor_held_oldest_age_seconds` | T | `BATCH_VENDOR_HELD_REDRIVE_ENABLED` | False parks holds; rollback past vendor failover requires route-table removal and drain (see provider module); never put provider work on GPU ring |
| `batch:quarantined` | `Q:quarantine_job`; provider `V:ProviderSttStore.settle`, `V:ProviderSttStore.terminal` | `R:RecoveryStore.prepare/start/settle`; dormant GPU expiry `R:expire_held_in_transaction` via `H:HeldDeadLetter.tick` | `held_deadline_at` for enabled GPU path; provider entry paths remain unstamped | T | T | `BATCH_HELD_DEAD_LETTER_ENABLED` | False stops new stamps/automatic GPU maintenance; manual requeue survives |
| `batch:dead` | `R:expire_held_in_transaction` for `dead_letter_reason=held_expired`; historical dead reasons predate this expiry writer | `R:RecoveryStore.requeue_quarantined` → `J:Scheduler.requeue_quarantined_in_transaction`; legacy `J:Scheduler.redrive_dead` | `held_deadline_at`, retained after expiry | `omi_batch_held_expired_units` (stock, not dwell) | `omi-batch-held-expired-volume` (agent) | `BATCH_HELD_DEAD_LETTER_ENABLED` for new held expiry/nightly GPU requeue | `merge_pending=true` keeps pre-4a re-drive possible; unrelated dead reasons excluded. Record reason `record_barrier_aged` retains `merge_pending=false`; private OIDC requeue-record, separate record inflow/stock alert. |
| `batch:dead/input_expiring` | `R:expire_input_in_transaction` via existing held sweep; GPU-quarantined or assignment-held staging input | Manual `RecoveryStore.requeue_quarantined` (GPU), target-restorable `ProjectionReleaseStore.release(operator=True)` (assignment), or existing exact-bundle client re-upload (GPU uploads) | `audio_staged_at + 29d`, else legacy `enqueued_at + 29d`; repair stamps the current object | `omi_batch_held_oldest_age_seconds{leg="staged_input"}` before terminal | `omi-batch-staged-input-age` warning above 21d | `BATCH_INPUT_EXPIRING_ENABLED` default on, plus existing held-sweep kill | Retained audio/results/paid history. No polling/nightly resurrection; no lifecycle change. [Runbook](../../docs/runbooks/held-staging-inputs.md). |
| `batch:privacy_blocked` | `database/batch_pipeline_recovery.py:quarantine_fenced.revoke`; `database/jobstore/postgres_store.py:PostgresStore.quarantine_fenced` privacy fence | Terminal; privacy owner only | none | none | none | No held switch bypasses privacy | Retain fence; no held requeue |
| `batch:partial_retired` | `database/record_partial.py:update_run` | Terminal placeholder; replacement units own work | none | none | none | `RECORD_AUDIO_PARTIAL_ENABLED` | Retain partial inventory lineage |
| `batch:committed` | `M:OrderedMerge.commit_next` | Job terminal; P/S still owe projection | none | none | none | No held-specific switch | Job commit is not conversation/finalization completion |

`recovery_state` is an orthogonal job field: `held` → `prepared` → `running`
→ `failed_held` or `recovered`; revocation can write `cancelled`
(`R:cancel_fenced_recovery`). Prepared/running intents never age-expire into
dead letters. Assignment holds can set `recovery_state=held` on a **committed**
job; that does not turn it into a worker quarantine.

### Projection receipt

| Machine:state | Entry writer | Exit writer | Deadline field | Dwell metric | Alert | Flag / kill switch | Rollback behavior |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `batch_projection:pending` | `M:OrderedMerge.commit_next`; re-drive `U:ProjectionReleaseStore.release` | `S:ProjectionSession.persist` | none | T | T | `BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED` controls expanded release | Reassignment respects binding and watermark |
| `batch_projection:persisted` | `S:ProjectionSession.persist` | `P:ProjectionStore.mark_enrichment`, `S:ProjectionSession.write_receipt` | none | T | T | Same release switch | Multipart suffixes still owe follow-ups; no age expiry |
| `batch_projection:ready` | `S:ProjectionSession.write_receipt`, `P:ProjectionStore.mark_enrichment` | `P:ProjectionStore.complete`, then `P:ProjectionStore.acknowledge` | none | T | T | No held-specific switch | Existing accounting/receipt fences |
| `batch_projection:quarantine_held` | `S:ProjectionSession.persist/write_receipt` | `U:ProjectionReleaseStore.release`; nightly `H:ProjectionHeldDeadLetter.tick` | `held_deadline_at` for assignment holds only | `omi_batch_held_oldest_age_seconds`; expired subset `omi_batch_held_expired_units` | `omi-pipeline-held-row-age` (page); expired volume (agent) | `BATCH_HELD_DEAD_LETTER_ENABLED`; release expansion separately `BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED`; ghost hint repair `BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED` (default OFF) | Physical state retained; capped attempt reset preserves pre-4b release eligibility. Committed assignment gate failures also stamp/expire under the same window and privacy/operator guards. |
| `batch_projection:completed` | `P:ProjectionStore.acknowledge.commit` | Terminal | none | none | none | No held-specific switch | Keep receipts; no automatic reopening |
| `batch_projection:erased` | `database/batch_pipeline_purge.py:_write_erased_result` | Terminal privacy disposition | none | none | none | No held switch bypasses privacy | This is explicit privacy deletion, never dead-lettering |

### Finalization job

Fenced job status and conversation `finalization_status` are separate from
conversation `status`. The existing reconciler is
`services/conversation_finalization.py:reconcile_listen_finalization_jobs`.

| Machine:state | Entry writer | Exit writer | Deadline field | Dwell metric | Alert | Flag / kill switch | Rollback behavior |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `finalization:queued` | `F:_create_or_get_finalization_intent_txn`, `F:_mark_finalization_retryable_txn`, `F:_resume_blocked_byok_job_txn`, `F:_grant_finalization_budget_requeue_txn`, `F:_defer_sync_revision_fence_txn`, `F:_claim_finalization_replay_txn` | `F:_claim_finalization_job_txn`, `F:_claim_finalization_replay_txn` | `reconcile_after_at` | `listen_finalization_oldest_nonterminal_age_seconds` | `omi-capture-oldest-nonterminal` (agent) | `LISTEN_FINALIZATION_REPLAY_ENABLED` for replay | False stops replay, preserves live admission |
| `finalization:leased` | `F:_claim_finalization_job_txn` | `F:_mark_finalization_completed_txn`, `F:_grant_finalization_budget_requeue_txn`, retry/dead-letter writers | `lease_expires_at` | `listen_finalization_oldest_nonterminal_age_seconds` | `omi-capture-oldest-nonterminal` (agent) | `LISTEN_FINALIZATION_DURABLE_ATTEMPT_CAP_ENABLED` | False restores legacy attempt accounting; lease/generation fences stay |
| `finalization:blocked_byok` | `F:_create_or_get_finalization_intent_txn`, `F:_claim_finalization_replay_txn` | `F:_resume_blocked_byok_job_txn`; `F:_abandon_byok_finalization_job_txn` | No entry deadline; default 14-day abandonment computed from last activity | `omi_finalization_byok_new_oldest_age_seconds` | `omi-finalization-byok-dwell-page` (page) | `LISTEN_FINALIZATION_BYOK_ABANDONMENT_ENABLED` | False stops disposition; resumed BYOK still lacks a durable consumer (4c PLANNED) |
| `finalization:dead_letter` | `F:_dead_letter_finalization_job`, `F:_abandon_byok_finalization_job_txn` | No current automatic requeue; general recovery PLANNED phase 4c | none; `terminal_at` is age anchor | `listen_finalization_jobs` (stock); `listen_finalization_oldest_dead_letter_age_seconds` | `omi-finalization-dead-letter-stock` (agent) | Attempt-cap and BYOK-disposition switches above; general requeue PLANNED | Keep transcript/audio, failure reason and fencing; no fabricated success |
| `finalization:completed` | `F:_mark_finalization_completed_txn`, `F:_complete_server_batch_capture_txn` | Terminal | none | none (not in nonterminal publisher stock) | none | No held-specific switch | Keep generation/fanout receipts |

### record_audio custody and conversation

These are field/reader views, not additional dead-letter shapes. Live producer
tokens retain their original proof rules in `RECORD_TOKEN_LEASE_MODE=off` (default).
In shadow, server-observed frame batches and custody appends stamp per-token
`last_signal_at`, `lease_expires_at`, and `signal_source`; shadow cannot expire.
Serve honors the `record-token-lease` uid cohort. A token is lease-dead only if
its lease lapsed AND heartbeat missed AND no append since the last signal.
Retained-tail/privacy proof remains mandatory for a complete seal. A late signal
re-activates its producer fence before bytes. Custody uploads acquire a separate
exact token before archive/staging; only durable acceptance bumps
`record_upload_revision` and clears that token. Refusals/failures clear without a
bump or late-append count; a crashed uploader remains fenced for its own lease.
Only serve creates these podless custody tokens; their own lease remains an
exit in off/shadow after rollback. Existing frame-token pod proof is unchanged
in off. A custody upload accepted after rollback still revises and schedules
recovery; the flag cannot revoke an already acquired custody obligation.
Memoized waits do no token IO. Custody heartbeats renew at most once per lease/2
per conversation, only on observed manifests or completed archive file appends.
Serve-only frames revise and reopen the row. If original input has already been
captured, both frames and accepted custody schedule the existing partial
continuation, regardless of conversation status, preserving original immutable
work. Uncaptured admission reads the current revision and validates it again
after staging; a stale staged plan must retry. Late-append telemetry is emitted
only after the durable frame window/object or accepted custody append commits.
Intentionally disabled archives are not custody appends and preserve the route's
original response, without a fence, revision bump or recovery job.
Late WAL holes are retained create-only against actual sample coverage, so
partial rows and interior gaps are processed without the tail-only gap-fill
ramp. Partial results retain their partial marker; no completeness is invented.
Off keeps old writes/decisions, and post-seal shadow frames only count.
Raw audio is never deleted. Off/shadow restore original frame-token seal authority
and retain the lease exit and accepted-byte recovery of existing custody tokens.
The active repair CronJob exports its bounded age sample and folded child probe
counters on its scraped metrics port; the idle worker scanner remains disabled.

| Machine:state | Entry writer | Exit writer | Deadline field | Dwell metric | Alert | Flag / kill switch | Rollback behavior |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `record_audio:capturing` | `A:set_record_upload_pending` (exact token) | Same function on exact-token finish; conditional `A:abandon_record_upload_session.commit` after eviction worker/futures settle | none by design | none for all live producers | none | `PUSHER_ABANDON_EVICTED_TOKENS` for conditional abandonment | Off leaves tokens fenced for finish/proven-dead repair |
| `record_token:capturing` | `A:set_record_upload_pending`; `A:renew_record_token_lease`; `record_custody_append.begin` | Exact-token finish clear; abandon attestation; computed lease lapse | nested `lease_expires_at` | `omi_record_token_lease_active` | `omi-record-token-lease-late-append` (page) | `RECORD_TOKEN_LEASE_MODE` | Off restores pod/abandon proof |
| `record_token:lease_lapsed` (computed) | Three quiet lease clocks | **seal** via `apply_seals` (full retained tail); **partial finish** via `finish_partial` (clear map, hourly coordinator); **re-activated** via frame renewal or custody fence + durable `record_custody_append.finish` (revision bump) | computed, never persisted | `omi_record_token_lease_expired_would_total` | `omi-record-token-lease-late-append` (page) | Same mode/cohort | No migration or audio deletion |
| `record_audio:seal_refused` | `A:seal_record_audio.commit` | `A:seal_record_audio` after producer finish | none; `record_seal_refused_at` is first-entry age only | `omi_record_seal_refused_age_seconds` (bounded job page, open rows only) | `omi-record-seal-refused-age` (agent, declaration) | `RECORD_SEAL_REFUSED_STAMP_ENABLED` | False stops stamps/observation, never seals or clears custody |
| `record_audio:abandoned` | `A:abandon_record_upload_session.commit` | `utils/batch_pipeline/record_seal_sweeper.py:sweep` repair discovery | none; `abandoned_at` is proof/age anchor | none | none | `PUSHER_ABANDON_EVICTED_TOKENS` | Existing exact-token/repair path; no age-only exit |
| `record_audio_orphan:capturing` | Derived proven-dead subset of `A:set_record_upload_pending` tokens | `utils/batch_pipeline/record_seal_sweeper.py:sweep` | none by design | none | none | No held-specific switch | Preserve producer and tail proof requirements |
| `record_audio:sealed` | `A:seal_record_audio`; proof-backed repair | `utils/batch_pipeline/live.py:admit_recording`; no-job manual repair only | none | `omi_record_seal_nojob_count` (no-job stock only) | `omi-record-nojob-stock` (agent) | No held-specific switch | Closed audio alone is not admission/publication |
| `record_audio:record_upload_failed` | `A:mark_record_upload_failed` | `utils/batch_pipeline/record_seal_worker.py:Worker.tick` proof repair | none | none | none | `RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED` | False keeps failure bit; reconnect-only retry remains a gap |
| `record_audio:record_audio_partial` | `database/record_partial.py:finish_partial` | `utils/batch_pipeline/record_partial.py:drain_partial` via B | Coordinator `next_inventory_at`, not conversation entry deadline | none | none | `RECORD_AUDIO_PARTIAL_ENABLED` | Retain partial inventory and pending phone bytes |
| `conversation:in_progress` | `C:create_in_progress_conversation` | `C:request_finalization`, stale-content reconciler | No deadline for every capture | none | none | No held-specific switch | Keep capture custody separate |
| `conversation:processing` | `C:admit_processing`, `C:create_processing_conversation` | `C:complete`, `C:fail_and_discard_processing`; fenced F terminal writers | Processing lease is not a universal dwell deadline | `listen_finalization_oldest_nonterminal_age_seconds` (job proxy) | `omi-capture-oldest-nonterminal` (agent) | Finalization switches above | Keep current generation and honest terminal outcome |
| `conversation:merging` | `C:begin_merge` | `C:complete`, finalization reconciler | none | none | none | No held-specific switch | Keep merge lineage |
| `conversation:completed` | `C:complete`, `database/conversations.py:persist_processing_result_with_lifecycle`, `F:_complete_server_batch_capture_txn`, fenced F terminal writers | Terminal status; late batch results can still arrive | none | none | none | `CONVERSATION_TERMINAL_FAMILY_MODE` for claim/persist only | Off restores legacy merge; completed is not proof of closed audio, result publication or successful enrichment. Phase 2a claim/persist stamp success; only explicit restore supersedes failure; late persist never regresses completed status |
| `conversation:failed` | `C:fail_and_discard_processing` | Terminal status | none | none | none | No held-specific switch | Retain failure/custody evidence |

The read-only `conversation_phase` vocabulary (`capturing`, `sealed`,
`processing`, `transcribed`, `complete`, `settled`, `discarded`, `quarantined`,
`dead_letter`, `failed`, `merged`) is derived by `utils/conversations/phase.py`;
it has no persisted phase writer. It must not create another held shape.

### Exact retained shapes and sanctioned CAS

Phase 4a, [#24736](https://github.com/BasedHardware/omi/pull/24736), merge
`b6b1539c`: `Q:quarantine_job` writes `state=quarantined`,
`recovery_state=held`, `merge_pending=false`, empty `token`, `lease_until=0`,
`quarantined_at` and `quarantine_reason`. With expiry enabled it stamps
`held_deadline_at=now+7*86400`; `R:RecoveryStore.settle` refreshes that window
on `failed_held`. Eligible legacy rows get a full window on first examination,
never immediate expiry based on capture age. Provider-STT holds are excluded
from GPU expiry/requeue.

`R:expire_held_in_transaction`, called through `R:RecoveryStore.expire_held`
and `RecoveryStore.checked`, rechecks content/ledger ownership, privacy,
dormant `held|failed_held`, no result/receipt/token, expired lease and no active
paid/operator intent. It writes `state=dead`, `dead_letter_reason=held_expired`,
`held_expired_at=now`, and **resets `merge_pending=true`** atomically. It keeps
`recovery_state`, deadline, encrypted sources and intent/attempt history.
`R:RecoveryStore.requeue_quarantined` calls the sanctioned
`J:Scheduler.requeue_quarantined_in_transaction` CAS: `state=ready`,
`available_at=now`, `merge_pending=true`, `token=''`, `lease_until=0`,
`held_requeued_at=now`, owner revision increment and one queue append. Recovery
history and expiry markers remain. The private worker-OIDC
`POST /v2/batch-pipeline/requeue-quarantined` uses this path.

Phase 4b, [#24745](https://github.com/BasedHardware/omi/pull/24745), merge
`3b09c0c5`: `S:ProjectionSession.persist` stamps assignment receipts with
`held_deadline_at=now+7*86400`. The inner receipt is `state=quarantined`,
`disposition=ambiguous_generation`, `quarantine_version=1`, with
`held_speech_seconds`, `speech_seconds=0` and `obligation_due_at=committed_at+900`.
The outer settled result remains `projection_state=quarantine_held`, with
`protocol_version=2`, `lineage_quarantine_version=1`; its committed job carries
`recovery_state=held`. Persisted multipart suffixes and privacy holds never
age-expire. `U:ProjectionReleaseStore.release` backfills a missing deadline with
a full window, then marks only aged, still-unrestorable eligible holds with
`held_expired_at=now`, `held_expired_reason=held_expired`. It retains physical
state, result/transcript, receipt/parts, audio, job and watermark. At
`MAX_RELEASE_ATTEMPTS=3` or above, that same one-time CAS saves the count as
`held_expired_release_attempts` and resets `projection_release_attempts=0`.
Already marked rows are never repeatedly reset.
Default-off `BATCH_PIPELINE_PROJECTION_RESTORABLE_CAP_EXPIRY_ENABLED` also routes
restorable holds at or above that cap through the identical eligibility fences
and deadline/expiry CAS. It requires `BATCH_HELD_DEAD_LETTER_ENABLED`; the
stamping or expiry pass never releases the row. Off retains the capped hold.
With this switch on, a privacy refusal or any nonempty `privacy_reason` on the
summary or any part refuses release and expiry without writes.
With this switch on, every ordinary release transaction rechecks the expiry
stamp and refuses marked rows without writes, including the other leg of the
same scan. Only nightly redrive with `dead_before` strictly after the marker
may release an eligible row. A falsy `None` tombstone is not an expiry stamp.

The same release helper is the sanctioned projection expiry/re-drive CAS;
`H:ProjectionHeldDeadLetter.tick` invokes it for previous-day marked rows.
Release still requires the original target to be restorable. It writes
`projection_state=pending`, `projection={}`, `projection_redriven_at=now`,
increments `projection_release_attempts`, clears block/deadline/expiry stamps
with falsy tombstones, removes only quarantined parts, clears job
`recovery_state=None` and preserves the owner watermark. Existing protocol
normalization/release-version fences still apply. A new assignment hold gets a
fresh deadline; this is not deletion of the retained result or audio.

Legacy **ghost hints** are a separate projection/held exit: a row whose hint
is `quarantine_held` but whose summary receipt is `ready` and has no quarantined
part owes ordinary discovery, not held expiry. In the existing
`U:ProjectionReleaseStore.release` transaction, only when the real-held gate
fails, recheck the hint, ready receipt, all parts, absence of a privacy refusal,
segment/binding/owner identity, committed job with recovery state other than
`held`, and finite `committed_at` at least 24 hours old. With
`BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED=true`, recheck the normal release
`_target_restorable` fence inside the transaction; an absent or unrestorable
target yields `target_not_restorable` with no writes. Only then write
`projection_state=ready` and `ghost_settled_cohort=<label>` in a **single
transaction.update**. The hint matches `hold_for_quarantine`'s ready-sibling write.
Receipts, parts, jobs, audio, attempt counters and watermarks stay intact. The
existing discovery/completion/publication/acknowledgement path rechecks its own
fences. This is never `held_expired`; nightly expiry does not settle ghosts.
`BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_WAKE_ENABLED` (default true) hands settled ids to the existing bounded follow-up tail; false restores discovery-only scheduling, with completion privacy fences unchanged.

| Result field | Rule |
| --- | --- |
| `ghost_settled_cohort` | String marker only, written atomically with a ghost hint flip; never read by serving or release logic and never added to non-ghost rows. |

`BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_COHORT` defaults to `g1`; valid labels
are 1-16 characters `[A-Za-z0-9_-]` (no trimming). Invalid values fall back to
`g1`; each committed fallback emits aggregate-only
`event=batch_projection_ghost_cohort outcome=invalid_fallback count=1`, outside
transaction retries, without the rejected value or row identifiers. This string
setting is not a kill switch. The selector's boolean kill switch stays OFF by
default. No cohort ceiling is added; lead2 controls rollout via the flag and cap.

Cohort counts use six separate equality-only COUNT requests: cohort total,
cohort + `ready`, cohort + `completed`, and one cohort + state request for each
blocked/incomplete state (`pending`, `persisted`, `quarantine_held`). Blocked is
the sum of those three per-state counts, never an OR or IN query. If any per-state
count is unavailable or invalid, the sum is UNKNOWN, never zero. Other/missing
states (including `erased`) are `total - ready - completed - blocked`, UNKNOWN if
any required count is unavailable or the counts are inconsistent. No new index
is added: each conjunction uses only simple equality filters, supported by
[single-field index merging](https://docs.cloud.google.com/firestore/native/docs/standard-index-overview#use_index_merging).
The emulator exercises all six query shapes but does not establish production
index availability. The canary fails closed to UNKNOWN on HTTP 400 or any
unavailable count. `completed` is durable acknowledgement after ledger completion.
Eligible sync rows traverse publication, but legitimate skip paths (for example
`source_deleted`) still acknowledge without publishing. It is not proof of
publication or user receipt. A current
completed stock count compared with a windowed sync-publish proxy is informational
only. Settled rows cannot be un-completed: flag rollback stops future flips but
cannot undo completed ledger/publication effects.

`GHOST_SETTLE_MAX_PER_PASS=16` is shared across both release legs. Default OFF in code
is count-only: **no extra queries** or document reads, no ghost writes; classify
using the job/result documents already read by the existing transaction. Existing
real-hold writes and cursor progress remain unchanged. The release summary adds
aggregate-only `ghost_settled`, `classified`, `skipped_by_class` and `age_buckets`.
Classified counts held-gate failures (including stale hints) not handled by
assignment deadline backfill/expiry; those use waiting/expired instead. Each
classified row gets exactly one skip class or a committed repair. Skip classes distinguish hint changes,
non-ready receipts, quarantined parts, `target_not_restorable`, privacy, identity, held/non-committed jobs,
invalid/young age, count-only, cap and nightly expiry. Age buckets for classified
rows are disjoint: 1d to <7d, 7d to <30d, and 30d+. Younger/invalid ages have no
bucket. Retry attempts never inflate counters. No row IDs or user data enter
these aggregates.

Rollout owner David approved one prod train in the 2026-11-07 16:24Z ruling
(bus de6f03, addendum c5c481). Prod backend-integration and the prod listen
serving chart declare true; dev remains count-only. Owner omi-pipeline reviews
within 24h of deployment (registry review 2026-11-09) using these summaries and the existing
`quarantine_held_rows`, `assignment_held`, `held_expired_rows` legs. Rollback:
set `BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED=false` on both serving roles
to stop future ghost hint repairs. Record dead-letter and assignment expiry
remain controlled independently by `BATCH_HELD_DEAD_LETTER_ENABLED`. Already
normalized hints and published sync results remain valid; publications are not
undone. These declarations do not prove deployment.
New atomic writers must keep the CI invariant: hint `quarantine_held` implies a
quarantined summary/part; only pre-fix legacy rows may violate it. Runtime release
also uses the 24h floor and authority checks, never an assumed epoch cutoff.

Both nightly helpers use the maintenance leader, 32-row pages, a five-minute
continuation cadence, durable cursors and post-work checkpoints. Only expirations
before UTC midnight qualify. Projection's unfinished cursor continues across
midnight and its helper continues with expiry disabled. GPU job automatic
maintenance stops with expiry disabled; manual requeue remains available.

Observability: `omi_batch_held_expired_total` counts committed expiry
transitions; `omi_batch_held_expired_units` counts retained job **plus projection**
stock; `omi_batch_held_expired_observed_at_seconds` timestamps successful samples.
The static log event is `batch_held_dead_letter` (GPU expiry/requeue loop);
projection uses `batch_projection` with `action=release_held|redrive_expired`.
`omi-batch-held-expired-volume` in
`charts/monitoring/alerts/batch-held-dead-letter.json` is **agent-only**: fresh
stock >100 or >10 expirations/30 minutes for five minutes. These are initial
thresholds, not production-calibrated values. No expiry metric proves recovery.

### Record barrier settlement (2026-11-07)

`utils/batch_pipeline/live.py:drain_recordings.admit_and_defer.defer` handles only the literal
`ValueError('capture upload/finalization barrier not closed')`. Under
`BATCH_HELD_DEAD_LETTER_ENABLED` (default true), the existing privacy-fenced
defer transaction stamps `record_dead_letter_deadline_at=now+14*86400` on first
failure. Missing/null deadlines, including legacy rows, receive the full window;
malformed/nonfinite/bool deadlines never authorize expiry. Only the current
admission lease may stamp or expire. At deadline it atomically writes
`state=dead`, `dead_letter_reason=record_barrier_aged`,
`record_dead_letter_at=now`, `merge_pending=false` in the existing job write.
This composes with #24863: the same barrier classification retains age-based
retry backoff; disabling shared settlement preserves that backoff. The barrier
message is defined once in `config/record_audio.py`; bool, nonfinite or missing
`enqueued_at` values are young/unknown, and future timestamps have zero age. Other
refusals and privacy blocks keep their original defer behavior. No new
loop, query, conversation/custody mutation or provider call is added to defer.

`database/batch_pipeline_record_dead_letter.py:requeue_record` is the sanctioned
CAS for this reason only: `dead` → `record_pending`, `available_at=now`,
`merge_pending=false`, with reason, terminal stamp and deadline cleared to null.
The normal store commit-boundary privacy fence rechecks owner, conversation and
privacy generation. Private worker-OIDC `POST /v2/batch-pipeline/requeue-record`
uses the existing stage-qualified `RedriveRequest`; it remains available with
expiry disabled. No GPU queue append or paid replay is issued. Requeue permits
ordinary admission after the cause is repaired. This pre-admission shape is
excluded from GPU redrive and `_terminally_held`, so it cannot acknowledge phone
custody as a successful/held transcript. Reverting the feature restores ordinary
retry for pending rows; already dead rows require this reason-aware requeue
before reverting if they must resume (older code does not recover this reason).

`omi_batch_record_dead_letter_total` counts successful committed flips, outside
retryable callbacks; stock `omi_batch_record_dead_letter_units` and freshness
`omi_batch_record_dead_letter_observed_at_seconds` are sampled by the existing
projection nightly helper on the maintenance leader at its five-minute cadence,
via one reason-filtered aggregate count. Flag false stops new
stamps, flips and stock queries, leaving previous gauge timestamps stale.
`charts/monitoring/alerts/batch-record-dead-letter.json` alerts agents on fresh
stock >100 or >10 new flips/30m for five minutes. All three metric families are
admitted by `deploy/cloud_run_gmp_sync.yaml` and the dev/prod main and sync
Stackdriver exporter prefix lists; the shared RunMonitoring profile already
keeps `omi_.*`. The declared metric inventory and producer-to-alert ingestion
contract test cover these names without claiming they were observed live.
Initial thresholds are not
production-calibrated. Record and held expiry share the existing held kill switch
(lead2 bus 258db3); this change adds zero env flags and leaves the flag budget
count unchanged.

### Assignment gate-failure settlement (2026-11-07)

In `U:ProjectionReleaseStore.release`, a real-held gate failure may still be a
committed assignment hold. Recheck binding/owner/segment identity,
`state=committed`, `recovery_state=held`, `projection_state=quarantine_held`, no
privacy refusal and no open speech/terminal/silence operator intent. Completed
receipts awaiting ghost discovery are excluded before stamping or expiry,
including count-only, cap and age/recovery-fenced ghost skips. Under the
existing `BATCH_HELD_DEAD_LETTER_ENABLED`, backfill `held_deadline_at` with a full
seven-day window, then write the identical `held_expired_reason=held_expired`
and `held_expired_at=now` markers (including the one-time attempt-cap reset).
Malformed anchors never expire. Persisted multipart suffixes remain excluded.
Physical result/receipt/parts, transcript, job, audio and watermark remain intact.
Committed inflow feeds `omi_batch_held_expired_total`, existing stock/alert and
nightly redrive selection. Markers alone never release through the original
assignment gate; nightly recovery still requires its target and receipt fences.

Cost per settled row, excluding transaction retries and existing scan/claim/
privacy reads: record settlement adds **zero reads**, one existing defer write
at stamp and one at flip (two writes across two observations, no extra write in
either transaction); requeue reads one job plus the existing privacy authority
and writes one job. Stock adds one aggregate query per five-minute leader maintenance tick, charged
by index entries, independent of per-row settlement. Ghost settlement adds zero
reads and one result update, capped at 16/pass; subsequent normal discovery,
ledger/publication/ack writes are separate. Assignment gate-failure settlement
uses the existing page document plus job/result reads (three per observation),
zero new reads or target lookup, one result update for backfill and one for
expiry; an already stamped row needs only the expiry update. None of these
settlement transitions calls GPU/STT/LLM or deletes retained artifacts.

### Flags, rollback and ownership rules

One flag per behavior: reuse the existing control for the same behavior, never
add a second lane-specific expiry/held switch. The 4a/4b shared switch controls
new held and record barrier deadlines/expiry and record stock sampling; it does
not disable legacy recovery. Ghost settle has its own independent switch,
`BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED`: the held switch controls record
dead-letter and assignment expiry, while the ghost switch controls only ghost
hint settlement. Neither switch disables the other behavior. Distinct release,
presentation and custody behaviors retain their distinct controls.

- Record dead-letter rollback: set `BATCH_HELD_DEAD_LETTER_ENABLED=false` on record-serving roles to stop new record stamps, flips and stock sampling; ordinary retries and private requeue remain.
- Assignment expiry rollback: set `BATCH_HELD_DEAD_LETTER_ENABLED=false` on serving and worker roles to stop new held deadlines/expiry and GPU automatic maintenance; existing projection recovery and manual requeue remain.
- Ghost settle rollback: set `BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED=false` on both serving roles to stop ghost hint writes; count-only classification and already published results remain, and record/assignment expiry continues.

The complete behavior-switch inventory for the machines above is below;
capacity, retry intervals and unrelated product cohort flags are not switches
for these retained shapes. Defaults are code defaults, not measured live values.

| Flag | Default | Kill-switch location / behavior when disabled |
| --- | --- | --- |
| `BATCH_HELD_DEAD_LETTER_ENABLED` | true | `config/policy/kill_switches.py:KILL_SWITCHES`, read by `config/batch_pipeline.py:batch_held_dead_letter_enabled`; set false on serving and worker roles: no new held/record deadlines/expiry, record stock sampling or GPU nightly pass; private record and manual GPU requeue and existing projection release/nightly recovery remain; ghost settle uses its own switch |
| `BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED` | true | `config/batch_pipeline.py:projection_hold_recovery_enabled`; false restores older release scope/attempt fences and conflict waiting policy |
| `BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED` | false | `config/policy/kill_switches.py`, `config/batch_pipeline.py:projection_ghost_settle_enabled`; false classifies existing reads only, no ghost writes or extra queries; record dead-letter and assignment expiry use the held switch independently |
| `PROJECTION_PRIVACY_REFUSAL_RESUME` | true | `config/policy/kill_switches.py`, `config/batch_pipeline.py:projection_privacy_refusal_resume_enabled`; off disables retry of stale privacy refusals; actual privacy fences remain unconditional |
| `BATCH_PIPELINE_HELD_TERMINAL_STATUS_ENABLED` | true | `config/policy/kill_switches.py`, `config/batch_pipeline.py:held_terminal_status_enabled`; false restores legacy status reading, never authorizes custody deletion |
| `BATCH_PIPELINE_HELD_PARTIAL_ENABLED` | true | `config/policy/kill_switches.py`, `config/batch_pipeline.py:held_partial_enabled`; false stops new partial-ledger settlement; healthy projected siblings stay visible |
| `BATCH_VENDOR_HELD_REDRIVE_ENABLED` | true | `config/batch_pipeline_vendor_failover.py:held_redrive_enabled`; false parks provider holds; no GPU requeue |
| `LISTEN_FINALIZATION_BYOK_ABANDONMENT_ENABLED` | true | `services/conversation_finalization.py:is_byok_abandonment_sweep_enabled`; false stops abandonment disposition, supplies no BYOK consumer |
| `LISTEN_FINALIZATION_DURABLE_ATTEMPT_CAP_ENABLED` | true | `config/listen_finalization.py:durable_attempt_cap_enabled`; false restores legacy attempt budgeting |
| `LISTEN_FINALIZATION_REPLAY_ENABLED` | true | `config/listen_finalization.py:replay_enabled`; false stops replay, preserves live admission |
| `PUSHER_ABANDON_EVICTED_TOKENS` | on | `utils/pusher_record_finish.py:retain_closed_record_drain`; off stops conditional eviction abandonment; live tokens never expire |
| `RECORD_AUDIO_PARTIAL_ENABLED` | true | `config/record_partial.py:enabled`; false stops partial finish/coordinator advancement; existing custody barriers remain |
| `RECORD_SEAL_REFUSED_STAMP_ENABLED` | true | `config/record_seal_rules.py:refused_stamp_enabled`; false stops refusal stamping/observation |
| `RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED` | true | `config/record_seal_rules.py:upload_failed_repair_enabled`; false preserves upload-failed bit |

**Legacy recoverability is mandatory:** an expired/held row must remain
recoverable by code predating its change, under the same custody/privacy/target
preconditions. Both 4a and 4b needed review fixes: 4a's `merge_pending=true`
retains `Scheduler.redrive_dead`; 4b's physical held state **and** one-time
capped-attempt reset retain pre-4b scan/release eligibility. A flag-off test alone
is insufficient: frozen pre-change code must recover the retained shape too.
Neither needs a backward data rewrite or a retained new helper after full revert.
Older protocols predating vendor failover or projection protocol fences have
their own drain requirements; this promise does not waive those fences.

**Nothing is ever deleted by dead-lettering.** No TTL, storage call, audio or
transcript deletion, custody acknowledgement, conversation-status change or
privacy-fence bypass belongs to 4a/4b. Finalization's existing fenced terminal
writer can close its conversation honestly; it still retains content. Explicit
user/account privacy deletion is a different authority. Held partial uploads
keep `processing/batch_unit_held` and phone custody until actual completion or
explicit deletion.

### PLANNED gates

- **Phase 2a implemented; PLANNED phase 2b — `terminal_family`:** claim and
  processor persist stamp backend-only success under the mode above. Routing
  the remaining terminal writer families through the claim owner remains gated
  on this table and legacy compatibility, including conversation completion
  versus audio/result/finalization obligations. No backfill is implemented.
- **PLANNED phase 4c — BYOK consumer + finalization dead-letter requeue:** gate
  on this table landing first, owner-reviewed credential custody/consumer and
  generation/lease CAS contracts, retained-content and pre-change recovery
  tests, and one switch per new behavior. The existing budget requeue is a fenced leased-to-queued transition
  before dead-lettering, not recovery of an already dead-lettered job or a
  durable BYOK consumer. Never put request-scoped BYOK credentials in durable queue metadata.
- **PLANNED phase 5A / 5B:** both are blocked on this contract before starting;
  concrete state/writer/deadline/metric/alert/rollback changes require this
  owner's CONTRACT.md PR and their prerequisite phase acceptance. This section
  grants neither a new held shape nor runtime/rollout authority, and does not
  invent unratified 5A/5B semantics.

## Owners

Batch record lane: intake, scheduling, merge, config (A); GPU execution and
payloads (B, `diarizer/batch_pipeline*.py`); projection and receipts (C);
privacy and retention (D) — see [README.md](README.md). Trip registry and
backtests: infra. Ramp steps and rollbacks: the lead, applied by the approved
operator lane. Recovery redrive of `failed_held`: the redrive owner named in each ramp packet.

## Not promised

- Real-time or first-summary deadlines (watch only through 50%).
- Speaker names for sync-off users, or naming parity with legacy, before 100%.
- Recovery of audio that never reached an accepted upload (device-side drops are
  the client WAL contract, `app/lib/services/wals/CUSTODY.md`).
- Automatic redrive of vendor-cause `failed_held` (operator redrive today).
- Exactly one vendor for language ID (Modulate today; self-LID #23460 is required from 50%).
- Live preview quality: retire-cohort preview is a preference shift ([ADR 0003](../../docs/adr/0003-retire-flag-is-preview-preference.md)).


### Dark projection hold observability (2026-11-08)

`BATCH_PIPELINE_PROJECTION_HOLD_LOG_ENABLED` defaults OFF. Explicit `true` adds
one INFO `event=batch_projection outcome=quarantine_persisted hold_reason=...`
after a successful quarantine disposition commit, including partial multipart
persists, and after a committed sibling acknowledgment transitions the summary
state to `quarantined` or its projection hint to `quarantine_held`. Rewriting an
already-held summary is silent, using the transaction's prior summary and hint.
The closed reasons are `ambiguous_generation`, `conflict`, `poison_head`,
`payload_contract`, and `sibling`. Transaction retries and receipt replays emit
no additional success line; no identifiers or content enter the new line.
Persisted dispositions and existing logs are unchanged.

`BATCH_TIMELINESS_ALL_TIME_COUNTS_ENABLED` independently defaults OFF. Explicit
`true` adds `omi_batch_timeliness_all_time_units{leg=...}` for
`quarantine_held_rows`, `assignment_held`, and `projection`. These are exact stock
counts across all epochs and ages, including units younger than the SLA. They
reuse the existing Firestore COUNT aggregation path: three unbounded count
aggregations per successful refresh by the leader, no document scan and no
queries on scrape. The companion requires `batch_timeliness_leader` on and this
replica's lease; with election off, or on a follower, no companion COUNT runs.
The timeliness alarm, cadence, election, freshness and existing epoch-scoped
gauge remain unchanged. This companion is diagnostic; there is no alert or
production metric-inventory requirement for it.
Companion counts run only after the legacy sample has succeeded and the epoch
gauges have published, so a slow or failed COUNT cannot delay or stale them.
Each failed count logs its bounded leg and exception type, omits that series,
and leaves other legs available. A refresh removes previously exported
failed-leg values; it never substitutes zero. A legacy sample failure keeps its
existing error behavior and runs no companion counts.

Both controls are registered in `config/policy/kill_switches.py`,
`config/feature-flags.yaml`, and `config/flag_budget.json`. They require `true`
in every parser mode; unset/false emits no new logs or series and performs no
extra queries. Neither uses `BATCH_HELD_DEAD_LETTER_ENABLED`.
No enablement is included: the lead owns a separate canary and expansion
proposal after review. Rollback: set each switch to `false`; logs stop and the
companion series disappears on collection. No data migration or cleanup.

## Terminal-only merge polling (dark)

`BATCH_HELD_POLL_SKIP_ENABLED` defaults OFF. ON, `fresh_pending` and transactional
`first_pending` exclude committed/dead/quarantined/privacy_blocked/partial_retired/provider_superseded.
Unknown strings stay visible; missing/null state is excluded in Firestore, Postgres and simulator.
**Before enabling: all four prod/dev poll indexes MUST be READY, real query plans MUST succeed,
and `scripts.batch_pipeline_poll_state_census --project PROJECT` MUST PASS (0).** Run from backend
with `.venv/bin/python -m`; on this host source `~/.local/bin/gcp-agent-env.sh ro-prod` first.
The read-only tool COUNTs pending minus pending-in-full-lifecycle-inventory per prod/dev jobs collection,
prints one combined PASS (0)/FAIL (n) line and exits 0/1; API errors propagate nonzero. No job reads/writes.
Dead GPU expiry/privacy fencing can retain merge_pending; recovery remains unchanged while merge/scheduler
head lookup can advance. Held ready/retry/vendor_held heads keep capture order/fresh waiting;
`held_merge_owners` always uses OFF. Oldest, held SLA gauges and stale-vendor watchdog are untouched.
Unavailable ON queries fall back to exact OFF; OFF errors propagate. Rollback: flag OFF restores old queries/reads.
No flag is replaced. Savings are Firestore-only, exclude index-entry costs, and stay booked at zero pending settled SKU.

The merge commit alone writes `results.fresh_capture = (job.fresh_capture is True)`;
unstamped jobs become backlog (`False`), without backfilling old results or changing
log/predecessor order. Its only new semantic reader is the fresh-delivery guard:
the serving maintenance leader counts fresh results committed 10–20 minutes ago
and the pending subset once a minute, publishing
`omi_batch_pipeline_fresh_{committed_window_total,unprojected_window_total,unprojected_ratio}`
and `omi_batch_pipeline_fresh_guard_sample_age_seconds`. Empty windows or failed
queries have no ratio; stale counts/ratios expire at 120 s. The default-on
`BATCH_PIPELINE_FRESH_GUARD_ENABLED` kill switch suppresses queries and all guard
gauges when off. Reader inventory and rollout proof requirements are recorded in
`docs/listen_pusher_pipeline/changes/2026-11-13-fresh-delivery-guard.md`.

The projection acknowledge also stamps `jobs.delivered_at` and
`jobs.delivered_in_target` in the transaction that sets
`projection_state=completed`. The only semantic reader is the delivered-share
sampler: the maintenance leader walks one bounded job-metadata page (admitted
20 to 5 minutes ago, capped at 5,000 rows) every 300 s and publishes
`omi_batch_pipeline_delivered_share_{ratio,admitted_units,units,truncated,sample_age_seconds}`
per route and language. A unit is delivered in target when its first
acknowledge is at most 300 s after `enqueued_at`; the stamp is sticky on replay.
Missing or failed samples never publish a healthy ratio. The default-on
`BATCH_PIPELINE_DELIVERED_SHARE_ENABLED` kill switch suppresses the page and all
gauges. See `docs/listen_pusher_pipeline/changes/2026-11-14-delivered-share.md`.
