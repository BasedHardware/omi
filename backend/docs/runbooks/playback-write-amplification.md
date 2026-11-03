# Playback write amplification and derived-audio expiry

Investigation: 2026-10-22. Source: `BasedHardware/omi` origin/main
`9b9dcd3e83cfdff862bbf90147454bdd4514ad30`. This is a code/metadata conclusion,
not a deployed-fix receipt. The storage-growth report supplied with the task and
the two-lane lead STATE were read before implementation. No deployment or lifecycle
change is part of this PR.

## Root cause

The default (PLAYBACK_ON_DEMAND_ENABLED=false) path creates UUIDv4 audio-file IDs
in `database/conversations.py::_finalize_audio_file_group` on every refresh.
`routers/pusher.py::_upload_batch` refreshes all groups after each chunk flush.
`process_conversation.py` and `utils/sync/pipeline.py` refresh groups again at
completion/sync. Identical source bytes therefore acquire different per-part
object names. The conversation fingerprint includes those IDs, so metadata-only
refreshes also defeat conversation-task deduplication. Pusher used the changed
fingerprint to rebuild the entire, growing conversation after each flush once
any artifact had been stamped. Progressive re-encoding has quadratic byte cost
as a recording grows. This is additional to the intentional part + dense
conversation representations needed by different clients.

The per-part worker *already* checks existence and serializes deliveries; polling
uses named tasks. They cannot dedupe a new UUID. The conversation worker formerly
used a mutable `conversation.mp3` key in eager mode and only reused it after a
matching Firestore stamp. Upload-success/stamp-failure therefore re-encoded and
overwrote on retry. Neither writer used a GCS create-only precondition.

Metadata proof from the 2026-10-20 00:32Z inventory (all retained generations):

| Measure | Per-part MP3 | Conversation MP3 |
| --- | ---: | ---: |
| Conversation directories | 867,714 | 837,740 |
| Distinct object names | 5,857,436 | 837,740 |
| Generations | 5,857,466 | 2,009,407 |
| Mean names / directory | 6.7504 | 1 |
| p95 names / directory | 22 | 1 |
| Maximum names / directory | 13,311 | 1 |
| Mean generations / name | 1.000005 | 2.3986 |
| Maximum generations / name | 2 | 683 |

Within each directory, grouping per-part objects by size yields **2,518,198 excess
names of equal size**, totaling **8,748,050,563,350 bytes (8.15 TiB)**. At most
3,375 equal-size names occur in one directory/size group. Equal size is strong
corroboration, not a cryptographic assertion of identical content. Separate
legitimate audio groups may also have equal sizes. Conversation generations total
14,876,269,332,147 bytes versus 2,150,518,641,588 bytes if only the largest generation
of each name were retained: **6.92x byte amplification**. Those generations often
contain progressively longer audio, so this is a retained-byte comparison, not an
exact count of identical encodes. The supplied report's 14.6x captured-hour
comparison is an encoding-rate equivalent, not an independently measured content
fingerprint duplication factor.

Only Storage Insights Parquet metadata was queried, with ro-prod. No target-bucket
object contents, account documents, identifiers in results, or Cloud Logging.
BigQuery job `bqjob_r13dc579f2e3bac6_000001a164074afd_1` (US) billed
177,228,218,368 bytes, approximately $1.01 gross at the supplied $6.25/TiB rate.
The SQL derives directory groups internally but emits only counts, dates and bytes.

## October 7 attribution and limits

On Oct 6 the inventory shows 176,385 part writes / 31,716 directories and
67,632 conversation writes / 31,121 directories. On Oct 7 this becomes
241,021 / 32,123 and 115,198 / 31,494 respectively. Bytes rise from
447,316,305,093 to 1,049,730,667,569 (parts), and 431,437,337,712 to
916,089,438,438 (conversation). That is 2.25x total bytes while the number of
conversation directories is nearly flat. The original report's broader weekly
comparison is 342 to 2,196 GiB/day, followed by 2,467 GiB/day.

The writer defects predate Oct 7: UUIDv4 groups date to the original private-sync
implementation (`52405c49e7b`, 2025-10-13); Pusher invalidation was added by
`d5afb91f212` on 2026-07-09. The Oct 3–10 history contains capture/continuation and
rollout changes, including #20837 (tiered capture, Oct 7 02:49 +07), #20882
(silence-pause reversal, 12:02 +07), #20902 (capture hardening), #20836
(keep-all sample 2% to 20%), and #20842 (episode notes at 1%). None introduces the
playback writers or their invalidation algorithm. A larger/longer capture or sync
workload can expose the existing amplification, but metadata cannot bind those
writes to an app version or trigger. **The specific rollout causing the Oct 7 step
is unproven**; timestamps alone do not establish it. The lead STATE records the
repeat-work fix #21886 as merged Oct 16 with PLAYBACK_ON_DEMAND still default off,
and archive/coalescing stages dark. Those later changes cannot explain onset.

## Trigger inventory

| Trigger | Writer path / conclusion |
| --- | --- |
| Open/play/precache | `routers/sync.py` precache and `/urls` -> `utils/sync/playback.py` -> named per-file and conversation tasks. Cache misses enqueue; repeated polls reuse names. |
| File download/export fallback | `download_audio_file_endpoint` -> `download_audio_file_response` -> artifact download, then enqueue on miss; HTTP 202 while pending. Inline mode rebuilds WAV/PCM directly. |
| Normal completion | `utils/conversations/process_conversation.py` -> create audio files -> `precache_conversation_audio` plus `enqueue_conversation_artifact_build`. |
| Sync and historical sync | `utils/sync/pipeline.py` final audio metadata -> same two eager task paths. Historical transcription can expose previously captured audio; it is distinct from silent stuck-finalization backfill. |
| Pusher chunk flush | Former `_upload_batch` -> new IDs -> fingerprint invalidation -> entire conversation rebuild. Removed by this PR; metadata refresh continues. `/urls` detects later source changes. |
| Explicit/smart conversation merge | `merge_conversations.py` and `smart_merge.py` enqueue the changed survivor's conversation version. |
| Stuck-conversation backfill | `scripts/stuck_backfill.py` -> lifecycle finalization with SILENT_BACKFILL. `processing_trigger.py` marks it recovery/reprocess; process_conversation's `capture_audio` guard skips audio recreation. Not an independent MP3 writer. |
| Episodes | `routers/episodes.py` and `utils/episodes/` use conversation/transcript evidence; no playback/merged writer or reader. Source conversation finalization can take the normal path above. |
| Daily recap | The notification/daily-summary job consumes conversation text; no playback/merged call. No independent audio writer. |
| Retries | Named tasks + run lock coalesce identical logical work. The old random IDs escape naming; stamp failure escapes the old conversation cache check. Destructive-operation deferrals retain their fence and delayed retry behavior. |

## Fix behavior

Source manifest identities and legacy-handle aliases apply regardless of the
on-demand rollout. New conversation objects use a SHA-256 key covering source
manifest/layout, timeline origin, and `storage.CONVERSATION_BUILD_FORMAT`. The
file list is canonically sorted before hashing. Bump this constant whenever
conversation gap collapse, span projection, or export settings change; source
identity alone cannot invalidate a changed assembly algorithm. The worker checks the immutable MP3 and
its spans manifest *before* encoding. Spans publish first as a create-only JSON
sidecar, then MP3, then the conversation stamp. A failed stamp can recover from
GCS without encoding. Create-only `if_generation_match=0` prevents overwrites
if duplicate workers outlive the run lock. Obsolete per-file tasks are skipped.
Pusher no longer starts full-conversation rebuilds on chunk flush. Metrics:
`omi_playback_writes_total{outcome="cache_hit|generated|skipped"}`, with no IDs. The backend-sync GMP export filter explicitly retains this counter.

Server metadata `conversation_audio_artifact_fingerprint` selects the immutable
object while client URL shapes stay stable. Existing legacy artifact keys remain
readable through old stamps. New stamps use the strong source fingerprint already
recognized by rollback readers, so they can also locate the immutable MP3. On-demand
rollout settings are unchanged. Per-file and dense conversation objects are both
retained for released clients; this PR does not collapse those two formats into
one incompatible API. No lifecycle rules or workflow files are changed.

## Force regeneration of a bad pinned object

Automatic repair: invalid JSON, empty manifests, and malformed/non-finite span
fields are cache misses. The worker deletes the observed MP3 and sidecar using
`if_generation_match` on each snapshot, then rebuilds. It also repairs orphan
sidecars. A competing replacement is protected by its new generation. This path
respects the account destructive-operation fence. A legacy MP3 missing a sidecar
gets one published after a single reconstruction; stamp retries then reuse it
without encoding again, even without the metadata marker.

A valid-looking manifest cannot detect bad audio bytes. For that incident, a
separately approved operator can force one exact conversation version to rebuild:

1. Use the approved operator tier and deployed backend environment. Scope the
   operation to the regional bucket and exact conversation/version; confirm the
   source chunks remain available. Avoid racing an active audio-merge run lock.
   This PR's investigation uses only ro-prod and performs none of these writes.
2. Snapshot generations for exactly
   `playback/<owner>/<conversation>/conversation-<artifact-fingerprint>.mp3`,
   that name plus `.manifest.json`, and
   `playback/<owner>/<conversation>/conversation.unavailable` (if present).
   Delete each snapshot with a generation precondition, never a recursive prefix:

   ```python
   # bucket is the explicitly scoped google.cloud.storage Bucket.
   snapshots = [blob for name in exact_names if (blob := bucket.get_blob(name)) is not None]
   for blob in snapshots:
       blob.delete(if_generation_match=blob.generation)
   ```

   On a precondition failure, stop and re-observe the pair; do not delete the
   newer generation automatically. Do not delete source chunks or edit the
   conversation stamp. The unavailable marker must be cleared or readers can
   continue reporting unavailable.
3. Request the normal `/v1/sync/audio/{id}/urls` endpoint. Its existence check
   returns pending and enqueues the rebuild; the successful worker re-stamps the
   existing doc. A consumed named-task tombstone can still suppress that enqueue.
   In that case enqueue the current schema-v2 payload with `enqueue_named_task`
   under a fresh one-off repair name and the audio-merge handler as OIDC audience.
   Use the current computed fingerprint, `on_demand=true`, and current
   `requested_at`; preserve the worker/run-lock path. Do not change a fingerprint
   merely to escape task deduplication or disable the run lock.
4. Verify a new object generation, a valid sidecar, a completed worker, and a
   newly resolved URL. Existing clients holding the deleted URL may need their
   normal refresh/retry action; this procedure does not remove the expiry blockers.

## Expiry verdict: BLOCKED for the no-user-visible-failure requirement

These are derived artifacts, but regeneration from chunks is conditional on those
chunks remaining available, decryptable and correctly referenced. Metadata-only
inspection cannot establish historical source completeness.

| Reader / call sites | Miss behavior | Verdict |
| --- | --- | --- |
| Backend `/v1/sync/audio/{id}/urls`, `_get_audio_urls_via_artifacts`, `_conversation_audio_urls_entry` | Checks MP3/WAV existence; absent artifacts become pending and enqueue tasks. Eager task names have no time epoch, so a recently consumed named-task tombstone can suppress regeneration after a young cache deletion. On-demand names have hourly recovery, which can still delay a retry in that hour. | Regeneration intent exists; seamless recovery is not guaranteed. |
| Backend file endpoint, `_get_artifact_download_payload` | MP3 404 -> valid legacy WAV -> enqueue -> HTTP 202. Inline `_get_inline_download_payload` and `get_or_create_merged_audio` regenerate from chunks. Missing source yields 404/unavailable. WAV existence/download race can propagate 404 after existence check. | Conditional recovery, not a no-failure guarantee. |
| Mobile playback `conversation_bottom_bar.dart::_pollPlaybackUrls`, `_loadAudioPlayer`, stream error handler | Polls new URLs for up to 90s; keeps resolved URLs/player sources in memory. Mid-stream missing/expired URL yields loadFailed and Try Again, with no automatic refresh. | **Blocker.** |
| Mobile sharing/export `conversation_detail/page.dart::_downloadAudio` -> `AudioDownloadService.downloadAndCombineAudio/_downloadFile` | Polls up to 60s before download; an HTTP 404/non-200 throws and shows audioDownloadFailed. No automatic URL refresh after a GCS failure. | **Blocker.** |
| macOS `LiveCapturePlaybackProvider.resolvePlayback`, `CapturePlayback` AVPlayer status observer | Resolver can return pending; failed player item displays “Check audio to refresh the link.” URLs stay in the player in memory; no automatic 404 renewal. | **Blocker.** |
| Web `ConversationDetailPanel.tsx`, `AudioPlayer.tsx`, `getConversationAudioUrlsWithPoll` | Resolves/polls pending entries, stores signed URL in component state. HTML audio onError shows “Failed to load audio”; Download opens that same URL directly. | **Blocker** for playback and export. |
| Shared-conversation URLs / text exports | No direct reference to these private derived prefixes found; generated API bindings are not consumers. Mobile audio share follows the explicit blocker above. | No additional durable derived-audio dependency found. |

Both MP3 URL helpers and `get_merged_audio_signed_url` call `_get_signed_url(...,60)`:
**60-minute v4 signed URLs**, also cached in Redis for that TTL. That is a URL
credential lifetime, not a guarantee the object will survive for the next hour.
A URL issued just before lifecycle expiry can fail while still signed. No automatic
404 regeneration occurs at a direct GCS signed URL. Released clients already
receive such URLs; a server-only writer fix cannot make that race seamless.

Live bucket metadata observed on Oct 22 already contains Delete merged/ age 3 and
Delete playback/ age 30, plus chunks/ Standard -> Coldline age 30. Soft-delete
retention is 0. This differs from the supplied earlier report. This investigation
made **no** bucket changes. An operator should review that existing state against
these blockers; this PR does not certify it safe to expire without visible failure.

## Expected bytes and verification limits

At 48 kbps, 3,668–4,281 captured hours/day corresponds to approximately
79.2–92.5 billion bytes/day (73.8–86.1 GiB/day) for one rendition, or
**158.5–184.9 billion bytes/day (147.6–172.2 GiB/day)** for the retained part plus
dense representations. This is a steady-source planning baseline after duplicate
rebuilds are removed, not a measured post-deploy forecast or upper bound. Old
conversation demand, real late-source versions, backfill, and gap-filled silence
add bytes; cache hits reduce new writes. No fixed write-rate promise follows from
metadata alone. Compare the new metric and next inventory after a separately
approved deployment. The supplied 1,255.70 GiB/day is net stock growth, not gross
bytes written; it should not be conflated with this forward-write estimate.

Initial focused verification: **243 tests passed across 12 files**, through
`cd backend && BACKEND_PYTEST_WORKERS=4 BACKEND_UNIT_TEST_FILE_LIST=<file-list> nice -n 10 ./test.sh`
wrapped in the workspace `omi-heavy` runner. Focused tests exercise stable identities with the rollout disabled, changed
sources, legacy aliases, create-only races, large spans, stamp-failure retry via
the actual FastAPI HTTP route, deleted conversations, and destructive-operation
fences. Local and CI receipts belong to the PR; no live user-audio canary ran.

Review follow-up verification: **147 tests passed across 8 affected files**
through the same four-worker `test.sh` runner. Added guards cover build-format
bumps, file-order invariance (including equal-start assembly), malformed sidecar
recovery on the final task attempt, generation-race protection, legacy sidecar
publication, and v1/v2 supersession through FastAPI HTTP.
