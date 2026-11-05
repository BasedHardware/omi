# Conversation speakers on the authoritative batch lane

Enrichment calls the existing stored-audio speaker resolver before summarization.
For transcripts with `final:batch:` provenance (including retained
`provider_speaker` scopes after resolution), `BATCH_CONVERSATION_SPEAKERS_ENABLED`
defaults on. The existing batch admission cohort determines which new records
reach this path. The optional whole pass adds a nested GPU cohort, described below; it makes no ASR call.
Retained-audio conversations use the existing audio/cache path. For sync-off
records, [ADR-0004](../adr/0004-sync-off-speaker-centroids.md) approves temporary
encrypted centroids under the additional default-on
`BATCH_SYNC_OFF_CENTROIDS_ENABLED` kill switch. The
[retention contract](../batch-voice-evidence-retention.md) defines their hard TTL,
scheduled/account erasure and bounded extraction before audio cleanup. Expired
or unavailable evidence leaves anonymous labels; no `audio_files` is required.

The resolver reads only verified, generation-pinned audio windows and reuses its
encrypted Omi-v2 embedding cache. It pools measured evidence within each original
unit label, then uses constrained acoustic clustering across units at the existing
cross-scope distance (0.60). One unit label stays together; distinct labels in one
unit cannot link transitively. Missing provenance and diarization gaps abstain.
Work retains the existing 45-second resolver budget, embedding/read caps and
cache; grouping additionally caps at 1,024 label groups and two seconds. A later
enrichment reuses the cache and immutable provider partition. Resolved transcripts
retain a durable `final:batch:conversation:<id>` scope. If optional encrypted unit
metadata is lost (including the existing 256-segment sidecar limit), the entire
prior conversation partition becomes the constraint graph: each prior group stays
whole and distinct prior groups cannot merge. New upload labels can still join a
prior group acoustically. This conservative fallback may preserve an earlier
over-split; it cannot silently relax batch authority. It adds no retained data or
storage-budget exception and emits a shared degraded-fallback event. The resolved
scope itself does not prove an upload audio clock; retained placement evidence is
still required.

The shared `name_centroids` matcher runs after grouping, with its existing
threshold, margin, five-second measured-evidence floor and joint owner
arbitration. Names never merge groups. Manual speaker IDs remain reserved and
manual receipts are reapplied before summarization and on persistence. Speaker
evidence serving cannot override this graph using roster-count or near-field
heuristics.

The lead deploys the backend image to the roles running conversation processing
and enrichment (Cloud Run backend, backend-sync, backend-sync-backfill and
backend-integration), plus Pusher. Pusher's legacy finalizer uses the same
resolver and must retain the constraints on a subsequent live finalization.
No GPU model or listen change is required by this fix.
Verify each traffic-bearing revision's release SHA; then verify the current batch
cohort's cross-unit speaker counts, named-owner/person attribution, manual edits,
abstentions and enrichment latency before expanding batch admission. Existing
`omi_conversation_speaker_resolution_total` and its reason/coverage logs measure
resolver completion; they do not prove human attribution accuracy. Qualify real
audio separately through the authorized staging fixtures; synthetic tests prove
constraints and identity policy only.

Per-window audio evidence: a manifest that disagrees with the listed objects abstains only the windows it
overlaps, for batch-authoritative conversations and beta clients. `SPEAKER_PER_WINDOW_ENABLED=false` restores
the whole-recording refusal; set it on processing services. Refusals appear by reason on the
`conversation_speaker_audio_evidence` log line.

Inside that cohort, a `sync:` segment refused only because `.batch.enc` overlaps it is proven and cut on
`.opus.enc` alone. A `final:batch:{unit}` scope does not identify a clock: `batch_sync_v1` desktop WAL uploads
also project that scope. CPU admission records `WorkItem.timing_store` from the actual audio source, and
projection stamps it on the storage-only `provider_speaker` dict. Built-in WAL decoding stamps `sync`;
retained live manifests stamp `batch` only when every reference is `.batch.enc` / `.batch.bin`. Alternate
decoders, unknown or mixed custody references and historical jobs remain unstamped. Generic staged
`audio_uri` values identify encrypted pipeline artifacts, not their timing store; no historical job reads
or inferred backfill are added.

An overlapping-store batch window is proven and cut only on its stamped store: `sync` uses `.opus` /
`.opus.enc`; `batch` uses `is_batch` / `.batch.enc` / `.batch.bin`. No stamp means the refusal stays. After
conversation resolution, the original unit scope and timing stamp in `provider_speaker` survive together;
a `final:batch:conversation:` scope alone supplies no proof. A selected-store coverage hole abstains only
its affected windows and never borrows the other store's audio. `SPEAKER_SYNC_STORE_ENABLED=false` restores
the native `sync:` refusal; `SPEAKER_BATCH_STORE_ENABLED=false` independently restores the `final:batch:`
refusal for either stamped store. Both default on inside the per-window cohort. The store-neutral
`conversation_speaker_store` log reports `batch_proven`, `sync_proven` and the total proof count.

Rollback: set `BATCH_CONVERSATION_SPEAKERS_ENABLED=false` on processing hosts.
That stops automatic batch linking/naming, including when speaker-evidence mode
serves. It preserves existing transcript and manual labels; it does not rewrite
historical conversations or undo already published names. No historical repair
or production flag mutation is part of this code change.


## Whole-conversation final pass

After the current resolver and speaker-evidence projection, before summary generation,
`BATCH_FINAL_PASS_ENABLED` defaults on beneath `BATCH_CONVERSATION_SPEAKERS_ENABLED`.
`BATCH_FINAL_PASS_PERCENT` defaults to 100 and uses the existing transcription-final-pass
UID hash bucket. This knob is independent of the retiring shadow/legacy-sync flags.
Persisted `final:batch:` authority reaches it during normal enrichment with either
sync setting; dedicated speaker-only retries run this pass with identity-only
persistence, without rerunning enrichment. Only the retained,
private recurring profiles described below may be learned after revalidation.

The adapter reads each unit's encrypted, generation-pinned staged audio and result,
placing that PCM and its words by the job's `capture_at`. It reconstructs exactly the
projection IDs: record origin keeps the original unit, WAL uses `split_result` and
its speech-span part IDs. Stored transcript offsets and lexical alignment never
place a unit. It does not assemble conversation `audio_files` or compare lossy playback
encodes with staged PCM. Native-record staging manifests still materialize their own
pinned sources and slices, with their original PCM digest checks.

Coverage is per positive-duration, batch-backed segment. Other lanes, point-only
segments and manual labels keep their existing authority. When some required
segments lack reconstructable evidence, covered segments may receive revalidated
updates; unplaced segments keep their labels. This reports `partial_coverage`,
includes `coverage` and `coverage_reasons`, leaves conversation-wide speaker
resolution unavailable, and performs no recurring learning. No reconstructable
words means no updates. Mixed-speaker segments and diarizer gap words also abstain
individually, with `failed_unassigned_words` if any remain; covered segments may
already have changed, and recurring learning is suppressed.

Expired, merged, shared or privacy-fenced references, conflicting overlapping
capture clocks, and read-budget failures refuse the whole invocation before
application. Shared-unit refusal is deliberately whole-pass, even if other units
are usable. Artifact privacy generation and deletion fences apply before/after
reads; references and expiry are rechecked after inference. Staged audio/results
retain their cleanup deadlines. Point words preserve transcript text but never
contribute voice evidence.

### Reading final-pass outcomes

`omi_transcription_final_pass_total{lane="batch",outcome=...}` records terminal
initial-pass outcomes. Dedicated retries record
`omi_transcription_final_pass_retry_terminal_total{outcome=...}` instead: each
idempotent obligation closes atomically with its durable counter increment. A
lost Firestore reply or process failure cannot lose or duplicate that count. The
existing maintenance sweep refreshes 16 fixed counter shards every two minutes,
including when no rows are due. Scrapes read only the process cache. Replicas
mirror the same cumulative totals: deduplicate with `max by (outcome)` before
computing increases, never sum the mirrors. Retry delivery does not also increment
the initial-pass counter. Together these record one terminal outcome per admitted
conversation obligation. `skipped_ineligible` calls are
outside the cohort and terminal counts. Durable `deferred_*` results are
nonterminal; inspect the subsequent speaker-only retry outcome rather than
treating a deferral as a failed or successful conversation.

For a one-hour outcome dashboard, add the initial per-instance increases and the
deduplicated durable retry increase. The `or` retains both streams because only
the initial stream has a `lane` label; the outer sum combines them by outcome:

```promql
sum by (outcome) (
  increase(omi_transcription_final_pass_total{lane="batch"}[1h])
  or
  increase((max by (outcome) (
    omi_transcription_final_pass_retry_terminal_total
  ))[1h:2m])
)
```

Gate on fresh durable observations too:
`time() - max(omi_transcription_final_pass_retry_terminal_observed_at_seconds)`.
Missing or older-than-six-minute observations are unknown, not zero retries or
success. Restart the full rollout observation window after deploying this metric
change; historical closed receipts are not backfilled. Terminal logs are
best-effort diagnostics; the durable aggregate is authoritative for retries.

| Outcome / code-owned reason | Meaning and operator action |
| --- | --- |
| `partial_coverage` | Some batch-backed segments were updated; unplaced segments retain labels. No recurring learning. Inspect `coverage_reasons` for missing jobs, changed projection IDs/text or point-word evidence. |
| `skipped_expired` | A required staged artifact expired or was cleaned. No updates; retries never extend retention. |
| `artifact_cleaned` (reason, not an outcome) | Cleanup tombstone: `expires_at` is the metadata TTL, not an audio lease. Appears under `skipped_expired`, including when that TTL is still in the future. Do not restore or accept deleted audio from the receipt. |
| `skipped_merged` | Projection receipts refer to another conversation after merge/split. No updates; do not infer ownership from current transcript offsets. |
| `skipped_shared_unit` | A staged unit includes receipts for another conversation. Whole-pass refusal protects its audio. The unit-skip counter separately measures affected units. |
| `deferred_transient` | Retryable Firestore/GCS/transport failure, elapsed artifact read deadline, or HTTP 408/429/5xx. Uses the bounded speaker-only outbox; other 4xx, TLS errors and structural caps stay terminal. |
| `deferred_custody` | The wake was acknowledged during a transient claim/settlement/reporting failure. The durable-row sweeper repairs it after recovery; it is not another inference attempt or terminal outcome. |
| `skipped_retry_exhausted` | The four-claim retry cap was reached without a terminal speaker result. Duplicate wakes cannot reopen the obligation. Slot-only exhaustion uses `skipped_slot_exhausted`. |

For read-only local diagnosis, use
[`testing/owner_lab/final_pass_repro.py`](../../testing/owner_lab/final_pass_repro.py),
which runs the real staged-unit reconstruction and final-pass path. The
[owner-lab instructions](../../testing/owner_lab/README.md#batch-speaker-final-pass-repro)
describe `0600` UID/secret/selection files, the write fence, stub versus HTTP
diarization and JSONL output. The stub checks plumbing, not diarization quality;
the harness captures application/learning/requeue calls and bypasses spend
admission. Inspect `read_wall_seconds`, `read_bytes` and `read_objects` alongside
coverage and code-owned exception locations; full private-cloud-sync audio is
not an equivalent reproduction.

Ordinary staged audio and results are scheduled for cleanup **24h after successful
projection**, for both sync settings (`retention.expire_completed_segment`). This is
separate from ADR-0004's temporary centroid TTL (24h after capture, shortened to 1h
after completion). Enrichment within the existing staged-artifact window can serve
sync-off too. Delayed enrichment after expiry abstains even if physical cleanup has
not run. A native-record audio manifest can live longer, but its result still has
the 24h window and every pinned source must remain available.

`run_final_pass` uses community-1 through `/v2/diarization`, unchanged centroid naming,
five-second evidence floor, thresholds, margin and joint owner arbitration. A manual
owner reserves the identity. Manual receipts and
stable segment IDs survive application under `final:batch:conversation:<id>`.
Whole-pass refusals, including incompatible embedding output, emit
`record_fallback` and retain all current resolver labels. Partial application
preserves unsupported segments as described above. There is
one nonwaiting process slot, a 600-second deadline, a 7200-second PCM ceiling
(`failed_too_long`), and a 480-unit limit checked before reference reads. This
supports two hours at a conservative 15-second average unit length (ordinary
units target 300 seconds). This invocation has its own read budget:
180 seconds, 320 MiB of encrypted objects and 1440 object reads, including result,
audio and nested manifest sources. It is independent of the playback reader's
30-second/64-MiB defaults. Reads stop before exceeding a byte/object limit and
refuse results arriving after the deadline. Elapsed read deadlines defer into
the four-claim speaker-only outbox; structural object/byte caps emit
`failed_read_budget`. Other structural coverage failures emit
`failed_incomplete_coverage`.
Budget reservations are Redis-atomic and charge attempts (including retries) before
GPU work: `BATCH_FINAL_PASS_DAILY_AUDIO_HOURS=1200`,
`BATCH_FINAL_PASS_HOURLY_AUDIO_HOURS=50`, `BATCH_FINAL_PASS_HOURLY_REQUESTS=1000`.
Invalid budgets or Redis failure refuse the pass. These are capacity limits, not
new admission. Per-unit diarization remains in place, so inference cost is additive.

Use the combined initial/durable-retry outcomes above, final-pass agreement
and latency with the same lane label, owner-parity delta, processing p95 enrichment
latency, and `omi_diarization_v2_queue_depth` for ramp decisions. The lead sets
the observation window before expansion. The sync GMP keep-list retains all
`_bucket`, `_sum` and `_count` series for `omi_transcription_final_pass_agreement`,
`omi_transcription_final_pass_latency_seconds` and
`omi_transcription_final_pass_owner_delta_ratio`. Source-backed names absent
from the historical metric capture are listed in the inventory's
`declared_metrics`; declaration alone does not prove live export. The lead sets
10%, then 50%, then 100%, expanding only after each cohort has a full observation
window with clean fallback rate, owner-parity delta, p95 enrichment latency and
diarizer-batch queue depth. GPU planning: admitted audio-hours/day × 0.03–0.042 =
GPU-hours/day; at the default 1200-hour daily ceiling this adds about 36–50.4
GPU-hours/day. This is compute time, excluding any pool floor/idle allocation.
Rollback with `BATCH_FINAL_PASS_ENABLED=false` (or percent zero); already-published
labels persist. The lead owns deployment and expansion; this PR changes no runtime
configuration or capacity.

## Recurring voices (ADR-0008)

After successful whole-pass revalidation, retained Omi-v2 clusters may publish
private sealed profiles. Unconfirmed profiles identify recurring speech only
with `recurring_voice_id`; they do not name anyone. Two distinct conversations
are required. Manual assignment binds to a confirmed person only after current
print consistency passes .35. No past conversations are rewritten for binding.
Follow-up: bounded identity-only retro-refresh of contributor conversations after confirmation.

Recurring IDs are revocable pointers: readers drop them when consent or an active
profile is missing, or after rejection. Opt-out additionally scrubs stored IDs
in pages of 100, with one transcript per transaction. If cleanup fails, repeat
the opt-out to retry the idempotent sweep; read-time revocation remains active.
Processing saves validate consent and active profiles in the transcript write
transaction, preventing late processing results from undoing the scrub. Profile
removal deletes the document atomically with its authority-index update.
Expiry and eviction leave only inert stored pointers until transcript deletion.

Controls: `SPEAKER_RECURRING_VOICES_ENABLED=false` stops new learning, matching
and recurring suggestions. `SPEAKER_RECURRING_PERCENT` defaults to 100 and uses
the final-pass UID hash, nested under `BATCH_FINAL_PASS_ENABLED`. Deletion,
retraction and opt-out cleanup remain active when killed. Rollback: set the kill
switch false; existing manual assignments remain user authority.

Before release the lead must enable the reviewed TTL policy for
`speaker_recurring_voices.expires_at` using `backend/scripts/batch_pipeline_ttl.py`
with `--policy backend/deploy/recurring-voices-retention.json`. Its default plan
mode is offline; apply requires separate operator authorization. Candidate
expiry is 30 days and maximum evidence age 90 days. Age checks immediately
refuse expired evidence; TTL removes sealed documents asynchronously. Profile
counts are capped at 25 per user, with at most three new candidates per pass.

The rollout lead owns any temporary cohort hold, expansion and before/after
read. Use stable UID-hash on/off cohorts on the same release and full observation
windows; export aggregate counters/events with cohort attribution at collection
time (never put user or voice IDs in Prometheus labels). Read together:

- `omi_final_pass_identity_speech_seconds_total{identity="owner|person|recurring|unnamed"}`:
  compare each identity's fraction of word-time speech, alongside total exposure.
- `Speaker Identity Confirmed`: corrected / (accepted + corrected), by cohort;
  a rising corrected share blocks expansion even if named speech improves.
- Recurring-origin `omi_speaker_tag_prompts_served_total` and
  `omi_speaker_tag_prompt_answers_total`: answer/served and accept/reject/skip
  shares over the same window. Existing identify copy and paid eligibility apply.
- `omi_conversation_speaker_resolution_voices{stage="resolved"}` and final-pass
  speaker count: compare distributions per conversation and speech duration.
- Profile lifecycle events and match outcomes, owner parity delta, final-pass
  failures and enrichment p95 remain guardrails. More recurring speech alone
  does not establish precision; a user answer is the confirmation signal.

Current counters contain no cohort dimension. `Batch Speaker Identity Mix`
records the four word-time totals, speaker count and `recurring_cohort=on|off`
without transcript text, vectors or voice IDs. Join product events by the
existing user identity and the same stable UID hash for card/confirmation
cohorts. Compare equal observation windows; fleet-wide counter totals alone
cannot prove a cohort effect.
The lead expands only after these precision checks and retention verification,
with review by 2026-11-17. No production read, deploy or ramp is part of this PR.
