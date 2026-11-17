# Future-date WAL recovery with unknown chronology

`SYNC_FUTURE_CAPTURE_CLAMP_ENABLED` defaults **off** in code and all twelve
bindings, under the quality lead's 2026-11-15 rollout ruling. Only filename
starts more than 24 hours ahead of receipt qualify for new future recovery.
The ordinary 600-second tolerance stays unchanged; stamps above 600 seconds
through exactly 24 hours ahead remain typed HTTP 400 `invalid_capture_time`.
Previously anchored sources retain their provenance when time catches up.
Nonfuture `_clke` estimates still use isolated untrusted admission when enabled.
No customer data migration or GPU image change is included.

## App contract and dates

Upload the existing multipart WAL bytes, codec/rate filename, optional frame
claims and custody proofs to `/v2/sync-local-files`. Untouched future filenames
with no `_clke` token are accepted. A requeued file estimated within the normal
skew window with a `_clke<run>_` token keeps its supplied estimate but uses
`estimated_source_isolated_v1`: per-source identity and untrusted chronology.
It cannot merge with a real conversation or use its estimate for coverage.
These marked estimates remain backfill, rather than taking fresh capacity.
A marked future run needs the stable client-device header. An unmarked file
needs no device/run identity: its owner and canonical single-file content HMAC
identify it. Recovered/estimated uploads may carry a stale `conversation_id`. The server
ignores that temporal target and admits only under isolated source identities;
it never writes or attaches to the supplied conversation.

For unmarked files an immutable transaction freezes a separate offset under
`users/{uid}/sync_assignment/capture-clock-<source-scope>`, making the full
file's decoded interval end at its first server receipt. Every file keeps a
separate source identity even if timestamps collide or other uploads contain
identical audio. Upload order is never represented as recording order. A retry
in a new directory or bundle retains that source's date and conversation ID.
The existing canonical file identity is reused; original basename/timestamp,
bytes, content IDs, source-frame offsets and custody proofs are unchanged.

Before admission, the router checks retained owner/source anchors in one
Firestore `get_all` batch, bounded to the existing 20-file upload limit. The
result is reused by the decoder, so the request does not repeat that lookup.
An over-limit lookup fails closed. A miss writes no anchor. A retained recovery
still validates account age and reads its immutable anchor transactionally,
without writing it. A new future source does the existing Auth account-age
read and one transaction read plus conditional anchor write per new scope.
An unanchored nonfuture estimate pays only the bounded lookup; it does not do
the Auth read, transaction read or write. The production recovery signal is
`OMI_SYNC_LANE_ADMISSIONS_TOTAL{reason="retained_capture_recovery"}`.

For marked future files `future_device_offset_v1` retains the revision-3
owner/device/run transaction: `offset = max(decoded raw end) - first receipt`.
All members subtract that immutable offset, preserving relative source order
and gaps across newest-first requests. A monotonic run token cannot denote
several resets. Mapped future audio waits with retryable 503; a discontinuity
over a day requires a new token. Firebase account creation bounds mapped
starts. Failed account/anchor reads or transactions return 503 with
`Retry-After: 30` before any job admission or successful ACK.

## Fences and response

The dedicated decoder validates strict future frame counts/full decoded durations
before yielding units. It never coalesces independent files. Normal marked
estimates use the existing strict decoder per original source. They may have
the bounded read-only retained-anchor lookup above, but without a hit they do
not do the Auth read, transaction read or future offset write, and inherit the
same identity/trust fences. Each source has
a content-derived `receipt-<HMAC>` source identity. Each admitted PCM unit/VAD part
has a stable distinct `receipt-part-<UUID>` row identity from its source, unit start
and VAD part index, independent of bundle IDs and provider word-edge jitter, so disconnected speech cannot overwrite another part.
Distinct sources never bind by synthetic time. Job, projection and assignment retain
`capture_time_trust=untrusted`. Conversation API serialization exposes that
optional field, and the existing `clock` field is `imported`. This means date
unknown; no app UI is added, so an older app shows the upload-date placement
without a newly introduced visual badge. The existing `sync_clock_run` row
partition also carries the opaque source identity, insulating upgraded rows
from older temporal assignment readers that already honor clock partitions.
This does not protect against old projectors dropping job trust before writing
a row. Every untrusted source also skips canonical/temporal episode attachment
and wall-clock duplicate proposals, so it remains a standalone Home recording.

Nearest/overlap discovery, absorption and time-only coverage cannot bind
another source in either direction. Same-source frame coverage remains valid
only under the existing exact provenance and custody proof. Synthetic time
never authorizes a covered-audio ACK. Before discarding a supplied conversation ID, recovery transactionally checks only
`users/{uploader}/conversations/{id}` and its same-account tombstone through the
existing privacy authority. Deleted sources return the existing ID-free HTTP 200
all-success deletion response, without staging or admitting new work. Other privacy
locks retain the existing typed 409. Live source IDs are persisted as
`capture_source_conversation_id`, strictly a privacy fence, not an assignment target.
Admission, artifact access, CPU compute authorization, job writes, projection and
status keep that source fence, so deletion during or after intake cannot resurrect
the audio. Missing/foreign IDs yield no source authority and no other account is read.
Exact-content retries without an ID use the retained content ledger and its original
result/source IDs to apply the same deletion authority; time overlap proves nothing.
The original batch content ledger gives atomic admission and re-ACK after a
lost reply. Timestamp refusals occur before that ledger and create no negative
receipt; replaying an original refused name is evaluated under the new policy.

Success uses the unchanged 202 schema: nonempty `job_id`, `status`,
`total_files`, `total_segments`, `poll_after_ms` and `lane`. The app marks the
WAL uploaded, clears refusal markers and polls; authoritative completed status
marks it synced and drains Pending. No success response is invented before
durable custody/admission. Unsupported or unavailable processing keeps the
phone copy on a non-success response; estimated uploads return retryable 503
instead of falling through to legacy processing without isolation. The server cannot retrieve a file an
older app stopped retrying: the client must resend/requeue it. Build 1563 general Sync retries only due refused rows; a direct row Sync skips
`uploadRejected`. Invalid-date refusal retries are spaced one day while the first
refusal is younger than seven days, then seven days, measured from the persisted
last attempt. Manual Sync does not override that eligibility.

## Reader-first rollout and same-day enablement

The code default, ten runtime overlay bindings and two listener chart bindings
are false. An image-only rollout is safe without a prerequisite operator env
mutation. Keep these committed false values while upgrading **and draining**
every CPU reader and admitter: Cloud Run `backend`, `backend-sync`,
`backend-sync-backfill` (including its CPU-guard-pinned image),
`backend-integration`, and GKE `backend-listen`. Include active/terminating
workers, traffic/tagged revisions, task URLs, operator restored-upload,
projection and speech-redrive jobs/checkouts. An unset `OMI_ROLE` mounts both
APIs and workers, so no service may be assumed reader-only.

Owner: **quality lead**. Target: **the same day as image rollout**. Once every
reachable reader and admitter serves an image containing this change, enable
**everyone in one config change** setting all twelve bindings true, regenerate
the runtime manifest and verify serving env/release readback. Do not leave a
David-only cohort or an unexpanded default-off gate overnight.

Required clean metrics after enablement: **zero new conversations from untrusted
sources sharing an episode or duplicate group with a trusted source**, and
**zero `invalid_capture_time` 400s for recoverable files**. Existing batch funding,
capacity and safety refusals remain separate signals. Qualify using every
traffic revision's `OMI_BACKEND_RELEASE_SHA` or source-proven image digest,
imageID, readiness, percentages, env and actual task targets.

At base `b23851a`, old `projection.py:588,696`, `live_upload.py:191` and
`scheduler.py:666` filter new fields from WorkItem. Old `projection.py:322-327`
then generates an ordinary capture-time identity and omits the clock partition.
Such an old projector is unsafe for a new recovery job. By contrast, an already
projected new row carries `sync_clock_run=<isolated part ID>`, and base
`utils/sync/live_overlap.py:36-42` compares that existing partition, preventing
time-only assignment to trusted rows. Old episode/duplicate readers lack the
new guards. This is a limited row-level fence, not an order-independent
capability gate. Adding an unknown WorkItem discriminator would also reject
jobs on the unchanged GPU image; this patch does not add that incompatible belt.
The committed false default and complete reader rollout remain mandatory.

The GPU scheduler/compute/OrderedMerge path does not project conversations and
updates the original full job map, retaining unknown fields. Its existing
compatibility is tested from source; the GPU image is unchanged and a live
serving digest has not been qualified here. Record-seal repair uses that image
and introduces no future trust-sensitive projector. The optional legacy sync
worker cannot receive these future jobs. Never allow fallback to legacy.

Deployment source of truth: `backend/runtime_images.json`, runtime-env
sources and charts. The backend deploy's `verify_backend_release_vector.py`
and `validate-backend-runtime-env.py --check-live-cloud-run` record CPU release
identity/traffic/env; include every actual task URL and GKE pod imageID, not
just the latest service spec or a chart release label. No deploy was performed
by this implementation lane.

## Rollback and bounds

Set the same admission switch false on every host to stop new recovery.
Already admitted offsets, IDs, trust and frame evidence remain immutable and
continue draining independently of the flag. Keep compatible CPU readers
while untrusted jobs or stored conversations remain reachable; do not roll back
to marker-dropping projectors or episode/duplicate readers, even after jobs drain.
No raw audio is renamed, rewritten or deleted by rollback.

No capacity tuning: the dedicated unit default remains 3600 seconds with the
existing 7200-second hard ceiling, and serving still supplies its configured
provider-unit limit. The recovery threshold remains strictly more than 86400 seconds ahead; the
ordinary tolerance remains 600 seconds by default, with the intervening band refused. No new numeric env or
queue/provider capacity is added. Existing early-clock request packing remains
unchanged; correcting its cross-request chronology needs a separate migration.

## Owner-visible cardinality

For N input files, expect N standalone recordings when each fits one decoded
unit and has one connected speech region. Disconnected speech or unit splitting
can produce more: rows = sum of connected projection parts over decoded units
of each file. Requests are bounded by 20 files, 64 MiB, 3,600 seconds and
360,000 WAL frames. For total bytes B, duration D and frame count F, the lower
bound is max(ceil(N/20), ceil(B/64MiB), ceil(D/3600), ceil(F/360000)); actual
packing can need more. About 20 hours requires at least 20 requests, with file
count/byte limits potentially higher. Actual retained file sizes were not read.
A 30-second-file example is 2,400 files, at least 120 requests and normally
2,400 standalone recordings; this is an example, not an owner measurement.

A future explicit, owner-scoped import-session container could reference these
unchanged source rows without merging trusted chronology or audio. It needs a
stable session identity across requests and Home rendering support; no such
container or app UI is built here, pending the lead's go.
