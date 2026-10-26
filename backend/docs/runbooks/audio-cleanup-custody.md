# Audio cleanup custody

Routine cleanup cannot use elapsed time or a terminal failure as permission to
delete accepted source audio. The October 2026 incident exposed a 480-second
timer started immediately after the legacy sync signed URL was minted, before
the provider returned. Batch cleanup was accidentally stalled by URI-less
receipts; repairing that exception without a preservation gate would release
incident-window originals.

## Legacy sync

The segment path no longer schedules a timer. Before decoding removes local
originals, the coordinator binds their SHA-256 to the content-addressed raw
archive paths returned by admission. On all-success completion it adds staging
MD5 checksums, then writes `staging_custody` beside the result in the same
owner-fenced content-ledger completion transaction. This bookkeeping is not
returned in the client result. Receipts larger than 128 KiB are omitted and
staging stays retained.

Cleanup rereads that ledger, requires an exact job and valid all-success result
(including no held audio), and verifies every original archive still exists
with matching plaintext SHA-256 metadata. It checks the original capture
window, compares each staged object's MD5 and deletes only its observed GCS
generation. A changed staging generation, missing archive, denied read, missing
receipt, partial result, failed job or old job without proof retains the object.
Cleanup errors do not change the successful transcript result. Derived VAD
blobs are covered by the same receipt and every original archive check.

This is a metadata custody proof based on the existing immutable raw-archive
writer, not a fresh decode/playback certificate. It does not prove that every
archived source sample appears in the transcript. Jobs without an original
archive (including consent-off paths and historical receipts) do not acquire
routine source-deletion authority. Zero-VAD early completions currently retain
staging too. No long timer or bucket lifecycle is introduced as a substitute.

## Capture-window hold

`AUDIO_CLEANUP_HOLD_ENABLED` defaults to `true`; only the explicit value `false`
disables the hold. `AUDIO_CLEANUP_HOLD_WINDOWS` is a comma-separated list of
timezone-qualified, inclusive `start..end` capture windows. Its default is:

```
2026-10-22T13:36:30Z..2026-10-24T07:16:00Z
```

The shared policy holds overlapping ranges, invalid/empty configuration and
missing or calendar-invalid capture provenance, including epoch-milliseconds
misreported as seconds. An unknown end is treated conservatively: a source
that starts before a window ends can overlap it. Thus legacy sources with only
a filename timestamp can remain held outside the exact incident start until
their end is certified. New batch artifact receipts include capture time and
duration; older receipts fall back to their job's capture metadata. Missing
jobs retain artifacts.

Before any routine or receipt-driven erasure, the receipt's `owner_key` must
match the canonical hash of its nonempty `owner_id`. Inconsistent rows are
flagged `cleanup_error=owner_mismatch`, retain their URI and leave the due
query. An untrusted erasure flag cannot grant authority to delete another
owner's data. A fallback job must have the same owner before its capture range
is trusted; inconsistent associations are flagged `capture_owner_mismatch`.
Direct owner-wide privacy purges remain authoritative.

Privacy erasure also pages artifacts by `owner_id`, using a single-field,
100-row bounded query. Thus a missing or inconsistent denormalized owner key
cannot hide a parked receipt from account or conversation erasure. Conversation
membership still filters each artifact, including segment bindings; other
owners and conversations are untouched. The configured owner-scoped URI guard
runs before metadata repair. A foreign reference fails the purge without
acknowledging deletion or granting another owner cleanup authority.

For an upload still in flight, privacy erasure first removes the current object,
then retains a canonical owner identity and explicit erasure outbox until the
bounded upload deadline, removing any receipt TTL. Its next cleanup bypasses the
hold and erases a late object. A verified URI-less erasure row removes metadata
without inventing an object path; ordinary URI-less receipts remain flagged.

Held batch rows retain their URI, lose any receipt TTL and re-enter the due
queue in one hour. This rotates a held first page so unrelated cleanup keeps
progressing. A URI-less receipt is flagged with `cleanup_error=missing_uri`,
removed from the due query and has its TTL removed for investigation; it is not
treated as a successful delete. Logs report bounded reasons without owner,
object or content identifiers.

The kill switch releases *only the window hold*, not legacy durable-success
or checksum/generation gates. Already parked batch rows recheck within an hour.
Do not remove the hold before the incident owner has reconciled custody. Keep
URI-less receipts for the repair owner; this change does not guess their URI or
erase their metadata.

## Bucket-policy release prerequisite

An application receipt does not stop a GCS lifecycle deletion. Historical
one-day lifecycle assumptions are not current policy guarantees:
a read-only metadata check on 2026-10-24 at 21:24Z found `syncing-local`
metageneration 15 with no lifecycle rule. Recheck policy before promotion;
source tests cannot establish live bucket configuration.

Run `backend/scripts/check_sync_staging_lifecycle.py` through a read-only agent
tier, with the release candidate's resolved bucket configuration. The guard
audits every configured `BUCKET_TEMPORAL_SYNC_LOCAL`, `BUCKET_AUDIO_DERIVED`
and `BUCKET_BATCH_PIPELINE`; repeated `--bucket` arguments supplement those
targets. Include any configured target absent from the audit environment.
For the known temporal target:

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
backend/.venv/bin/python backend/scripts/check_sync_staging_lifecycle.py --bucket syncing-local
```

Keep its timestamped JSON receipt before the lead-owned post-T3b promotion. It reads bucket
metadata only and emits counts, metagenerations and policy digests, with no
bucket/env values, prefixes or provider diagnostics. Missing metadata,
lifecycle `Delete` actions and bucket retention/default holds that could block
privacy erasure fail the guard. It never lists, reads, copies or restores
objects, changes policy, or uses the interactive human identity.

Do not substitute a GCS retention lock or object hold for this application
hold: privacy erasure must remain possible immediately. The rollout lead owns
any separately authorized policy remediation and must not promote an unsafe
or unaudited staging target.

## Privacy precedence and release

Explicit boolean `erasure_requested` batch cleanup bypasses the hold. Direct conversation/account
purges, including owner-scoped all-version GCS erasure, do not call the routine
hold or the legacy success verifier. Privacy erasure remains immediate and
retryable, even for incident artifacts or unknown capture timestamps.

The rollout lead owns merge and deployment after T3b. First deploy the backend
image to every API role serving conversation/account privacy erasure, including
backend, so owner-index artifact purges are reachable before cleanup can park
malformed legacy keys. Then deploy backend-sync, backend-sync-backfill and the
batch-serving integration host. Pusher/listen outbox changes are owned separately. No workflow,
production env, bucket retention, restore or historical data mutation is part
of this change. Old daemon timers already resident in an old process disappear
only when that process is replaced.

After release, verify the running release identity on every serving revision,
check `sync_staging_cleanup` and `batch_cleanup` reason logs, confirm the
incident artifacts remain present, confirm non-held cleanup advances, and run a
privacy-erasure synthetic canary through the approved release harness. Source
tests and CI do not establish deployed artifact preservation or playback.
