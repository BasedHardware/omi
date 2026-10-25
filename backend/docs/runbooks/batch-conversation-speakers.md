# Conversation speakers on the authoritative batch lane

Enrichment calls the existing stored-audio speaker resolver before summarization.
For transcripts with `final:batch:` provenance (including retained
`provider_speaker` scopes after resolution), `BATCH_CONVERSATION_SPEAKERS_ENABLED`
defaults on. The existing batch admission cohort determines which new records
reach this path. No additional account cohort or ASR call is introduced.
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

Rollback: set `BATCH_CONVERSATION_SPEAKERS_ENABLED=false` on processing hosts.
That stops automatic batch linking/naming, including when speaker-evidence mode
serves. It preserves existing transcript and manual labels; it does not rewrite
historical conversations or undo already published names. No historical repair
or production flag mutation is part of this code change.
