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
sync setting; bounded identity-only retries do not run it. Only the retained,
private recurring profiles described below may be learned after revalidation.

The adapter reads each unit's encrypted, generation-pinned staged audio and result,
placing that PCM and its words by the job's `capture_at`. It reconstructs exactly the
projection IDs: record origin keeps the original unit, WAL uses `split_result` and
its speech-span part IDs. Stored transcript offsets and lexical alignment never
place a unit. It does not assemble conversation `audio_files` or compare lossy playback
encodes with staged PCM. Native-record staging manifests still materialize their own
pinned sources and slices, with their original PCM digest checks.

All unit artifacts and every conversation segment must be accounted for before any
label changes. Missing, expired, privacy-fenced or unplaceable units, conflicting
overlapping capture clocks, and exhausted read budgets leave **all** resolver labels
unchanged. Mixed-speaker segments and diarizer gap words individually abstain after
a complete input assembly. Artifact privacy generation and deletion fences apply
before/after reads; references and expiry are rechecked after inference. Staged
audio/results retain their cleanup deadlines; the separate recurring-profile
write follows successful revalidation as described below.

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
Every failure, including incompatible embedding output, emits `record_fallback`
and retains current resolver labels. There is
one nonwaiting process slot, a 600-second deadline, a 7200-second PCM ceiling
(`failed_too_long`), and a 128-unit limit. This invocation has its own read budget:
180 seconds, 320 MiB of encrypted objects and 512 object reads, including result,
audio and nested manifest sources. It is independent of the playback reader's
30-second/64-MiB defaults. Reads stop before exceeding a byte/object limit and
refuse results arriving after the deadline; exhausted budgets emit
`failed_read_budget`, other coverage failures `failed_incomplete_coverage`.
Budget reservations are Redis-atomic and charge attempts (including retries) before
GPU work: `BATCH_FINAL_PASS_DAILY_AUDIO_HOURS=1200`,
`BATCH_FINAL_PASS_HOURLY_AUDIO_HOURS=50`, `BATCH_FINAL_PASS_HOURLY_REQUESTS=1000`.
Invalid budgets or Redis failure refuse the pass. These are capacity limits, not
new admission. Per-unit diarization remains in place, so inference cost is additive.

Use `omi_transcription_final_pass_total{lane="batch"}` outcomes, final-pass agreement
and latency with the same lane label, owner-parity delta, processing p95 enrichment
latency, and `omi_diarization_v2_queue_depth` for ramp decisions. The lead sets
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
