# Future-date WAL recovery with unknown chronology

`SYNC_FUTURE_CAPTURE_CLAMP_ENABLED` is an on-by-default kill switch. V2
batch uploads beyond `SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS` (600 seconds
by default) enter receipt recovery, including stamps only 601 seconds ahead.
There is no 24-hour hole: clock error magnitude does not establish correctness.
Within-tolerance skew, pre-2024 placement and deprecated V1 are unchanged.
False/0/off/no restores typed HTTP 400 `invalid_capture_time` for new future
admissions. The twelve dev/prod declarations are true, category `ops_kill`.
No customer data migration or GPU image change is included.

## App contract and dates

Upload the existing multipart WAL bytes, codec/rate filename, optional frame
claims and custody proofs to `/v2/sync-local-files`. Untouched future filenames
with no `_clke` token are accepted. A requeued file estimated within the normal
skew window with a `_clke<run>_` token follows the existing estimated-time path.
A marked future run needs the stable client-device header. An unmarked file
needs no device/run identity: its owner and canonical single-file content HMAC
identify it. Do not attach an unrelated explicit conversation target.

For unmarked files an immutable transaction freezes a separate offset under
`users/{uid}/sync_assignment/capture-clock-<source-scope>`, making the full
file's decoded interval end at its first server receipt. Every file keeps a
separate source identity even if timestamps collide or other uploads contain
identical audio. Upload order is never represented as recording order. A retry
in a new directory or bundle retains that source's date and conversation ID.
The existing canonical file identity is reused; original basename/timestamp,
bytes, content IDs, source-frame offsets and custody proofs are unchanged.

For marked future files `future_device_offset_v1` retains the revision-3
owner/device/run transaction: `offset = max(decoded raw end) - first receipt`.
All members subtract that immutable offset, preserving relative source order
and gaps across newest-first requests. A monotonic run token cannot denote
several resets. Mapped future audio waits with retryable 503; a discontinuity
over a day requires a new token. Firebase account creation bounds mapped
starts. Failed account/anchor reads or transactions return 503 with
`Retry-After: 30` before any job admission or successful ACK.

## Fences and response

The future-only decoder validates strict frame counts/full decoded durations
before yielding units. It never coalesces independent files. Each source has
a content-derived `receipt-<HMAC>` conversation identity; projection parts of
that source may append to that same identity, but distinct sources never bind
by synthetic time. Job, projection and assignment retain
`capture_time_trust=untrusted`. Conversation API serialization exposes that
optional field, and the existing `clock` field is `imported`. This means date
unknown; no app UI is added, so an older app shows the upload-date placement
without a newly introduced visual badge. The existing `sync_clock_run` row
partition also carries the opaque source identity, insulating upgraded rows
from older temporal row readers that already honor clock partitions.

Nearest/overlap discovery, absorption and time-only coverage cannot bind
another source in either direction. Same-source frame coverage remains valid
only under the existing exact provenance and custody proof. Synthetic time
never authorizes a covered-audio ACK. Existing deletion/privacy fences apply.
The original batch content ledger gives atomic admission and re-ACK after a
lost reply. Timestamp refusals occur before that ledger and create no negative
receipt; replaying an original refused name is evaluated under the new policy.

Success uses the unchanged 202 schema: nonempty `job_id`, `status`,
`total_files`, `total_segments`, `poll_after_ms` and `lane`. The app marks the
WAL uploaded, clears refusal markers and polls; authoritative completed status
marks it synced and drains Pending. No success response is invented before
durable custody/admission. Unsupported or unavailable processing keeps the
phone copy on a non-success response. The server cannot retrieve a file an
older app stopped retrying: the client must resend/requeue it. Manual Sync
retries eligible rows now; otherwise the existing retry scheduler applies.

## Reader-first deployment, with final admissions on

An old generic CPU job reader can discard the trust marker; a new optional
field alone cannot exclude it. Deploy in this exact order:

1. Temporarily apply `SYNC_FUTURE_CAPTURE_CLAMP_ENABLED=false` to every
   reachable admission host. This is a deployment override, not the committed
   steady-state configuration. Verify the false value on all traffic targets.
2. Roll and qualify all CPU readers on the new source: Cloud Run `backend`,
   `backend-sync`, `backend-sync-backfill`, `backend-integration`, and GKE
   `backend-listen`, including terminating pods, active CPU jobs, task URLs and
   tagged revisions. Operator restored-upload/projection/speech-redrive
   checkouts must also use the new build before operating on future jobs.
   Ordinary/early job and RPC envelopes retain old-reader compatibility while
   admissions are false; tests compare them to the fresh-main baseline.
3. Record every traffic revision's `OMI_BACKEND_RELEASE_SHA` or build-proven
   source digest, imageID, readiness, percentages and environment. No unknown
   reachable CPU projector may remain. Apply this commit's true bindings to
   all five hosts (ten environment overlay values and two listener chart
   values), regenerate the runtime manifest, and verify serving readback.

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
until that work drains; do not roll back to marker-dropping projectors.
No raw audio is renamed, rewritten or deleted by rollback.

No capacity tuning: the dedicated unit default remains 3600 seconds with the
existing 7200-second hard ceiling, and serving still supplies its configured
provider-unit limit. The recovery threshold changes from 86400 seconds to the
existing normal tolerance (600 seconds by default). No new numeric env or
queue/provider capacity is added. Existing early-clock request packing remains
unchanged; correcting its cross-request chronology needs a separate migration.
