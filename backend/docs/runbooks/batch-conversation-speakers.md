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
`.opus.enc` alone. `final:batch:` segments stay refused: desktop record units are timed on `.batch.enc` and the
conversation does not say which store timed a segment. `SPEAKER_SYNC_STORE_ENABLED=false` restores the refusal.

Rollback: set `BATCH_CONVERSATION_SPEAKERS_ENABLED=false` on processing hosts.
That stops automatic batch linking/naming, including when speaker-evidence mode
serves. It preserves existing transcript and manual labels; it does not rewrite
historical conversations or undo already published names. No historical repair
or production flag mutation is part of this code change.


## Whole-conversation final pass (sync-on slice)

After the current resolver and speaker-evidence projection, before summary generation,
`BATCH_FINAL_PASS_ENABLED` defaults on beneath `BATCH_CONVERSATION_SPEAKERS_ENABLED`.
`BATCH_FINAL_PASS_PERCENT` defaults to 100 and uses the existing transcription-final-pass
UID hash bucket. This knob is independent of the retiring shadow/legacy-sync flags.
Only persisted `final:batch:` authority with private cloud sync reaches it during
normal enrichment; bounded identity-only retries do not run it. Sync-off
continues using ADR-0004's temporary centroid resolver. No enrollment is published.

The adapter assembles `audio_files` through `iter_audio_chunk_pcm`, separately for
live PCM, sync Opus and raw stores. Like the shadow worker it trims duplicate leading
samples and preserves gaps. It replays each encrypted, generation-pinned unit result's
words and stable projection IDs, and requires exact decoded unit PCM equality on a
fully covered store interval. Stored transcript offsets and lexical alignment never
place a unit. Only one proven store is diarized per conversation; units from other
stores, missing/expired artifacts, mixed-speaker segments and words in gaps retain
the current resolver labels. Optional provider metadata loss also abstains. The
artifact adapter's live privacy generation and deletion fences apply before/after
reads and references are rechecked after inference. This writes no artifacts and
never extends an existing cleanup deadline. Sync-on still needs its staged result
and audio/manifest; enrichment after their cleanup abstains.

`run_final_pass` uses community-1 through `/v2/diarization`, unchanged centroid naming,
five-second evidence floor, thresholds, margin and joint owner arbitration. A manual
owner or an owner in an unplaced unit reserves the identity. Manual receipts and
stable segment IDs survive application under `final:batch:conversation:<id>`.
Every failure, including incompatible embedding output, emits `record_fallback`
and retains current resolver labels. There is
one nonwaiting process slot, a 600-second deadline, a 7200-second PCM ceiling
(`failed:too_long`), 128-unit/read limits, and the existing bounded audio reader.
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
