# As-captured audio and backend-sync cost trial

Owner: David approves cohorts; Claude deploys and ramps. Canonical capture stays
in `BUCKET_PRIVATE_CLOUD_SYNC` (the existing US multi-region bucket), indefinitely
except user-requested conversation/account deletion.
Training use is **not authorized** by storage consent. No age deletion or
historical rewrite is part of this change.

## Phases and compatibility

Per David's 2026-10-22 as-captured ruling (P71), `AUDIO_ARCHIVE_LIVE_ENABLED`
and `AUDIO_ARCHIVE_READ_ENABLED` default **on** as fleet kill switches: the
original Opus capture is dual-written next to the decoded PCM everywhere, and
readers prefer it, without a percent cohort. Setting either to `false` is the
rollback. The remaining phases stay default-off staged rollouts behind their
enable plus the common deterministic cohort (`AUDIO_ARCHIVE_PERCENT` (0),
`AUDIO_ARCHIVE_UID_ALLOWLIST` (empty)):

| Enable | Behavior |
| --- | --- |
| `AUDIO_ARCHIVE_LIVE_ENABLED` (default on) | Dual-write original Opus WAL packets or lossless PCM FLAC alongside today's PCM. Packs are bounded at 16 MiB, partitioned by owner/conversation/UTC hour/channel; tails flush on disconnect. |
| `AUDIO_ARCHIVE_READ_ENABLED` (default on) | Prefer checksum-verified raw coverage for span-bearing legacy chunks in merge, playback, and final-pass consumers of the shared decoder. Missing/incomplete raw keeps PCM. |
| `AUDIO_ARCHIVE_STOP_PCM_ENABLED` + `AUDIO_ARCHIVE_STOP_PCM_PERCENT` (default off/0) | Requires READ; ramps against its own percent (not `AUDIO_ARCHIVE_PERCENT`, which COALESCE pins at 100). Skip a PCM batch only after committed raw verifies complete coverage and the live capture-PCM SHA matches (or raw decode matches every byte). Missing raw, checksum, rate, span, or decode mismatch retains today's write. |
| `AUDIO_ARCHIVE_SYNC_ENABLED` | v1/v2 SD/offline uploads archive original file bytes before decode/acceptance; lossy backend Opus chunks become derived renditions. Existing mobile-batch archival remains mandatory. |
| `AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED` | Route merged/playback caches, sync renditions and new intake staging to `BUCKET_AUDIO_DERIVED`. Canonical raw stays multi-region. |
| `AUDIO_ARCHIVE_COALESCE_ENABLED` | Share concurrent identical file rebuild results, including failures; released admission permits retry. Existing fingerprint-named Cloud Tasks and distributed conversation leases still cover cross-instance rebuilds. |
| `AUDIO_ARCHIVE_SEPARATE_MERGE_ENABLED` | Route admitted merge tasks to `AUDIO_MERGE_WORKER_URL` (full `/v2/audio-merge-jobs/run` URL). Non-admitted tasks retain `AUDIO_MERGE_HANDLER_URL`. |

Stored-format decode support is permanent, with raw playback gated by READ.
After phase C, rollback STOP_PCM first and retain READ for owners with raw-only
historical audio until PCM has been regenerated and verified. Never disable
READ for that cohort prematurely. Regional rendition reads survive write rollback. Keep destination bucket/worker URL configuration while
old objects/tasks exist. Stage C cannot remove already-written PCM and does not
assume an hour of volatile raw is durable. Stage C queues supervised 60-second part commits within each hour without blocking
the receive/STT loop. Pusher retires PCM only if the commit finishes before its
batched upload; otherwise PCM stays. The archive tail flush runs after STT drain, outside its shutdown deadline. Whole-pack capture-PCM hashes
allow identity verification across stateful Opus decoder boundaries without
requiring a second lossy encoding. Consequently savings depend on
committed coverage at the time pusher uploads; this trial must measure that
coverage before claiming the full 115.2→13.2 MB/hour reduction. No device WAL
retention capability is assumed, and no uplink is paused.

Metadata includes codec/rate/channels/frame size, device/firmware/app version,
capture bounds, frame and gap counts, conversation link, storage consent scope,
state/version and plaintext SHA-256. Missing old-client provenance is explicitly
`unknown`, not a fabricated firmware, clock, gap-free assertion or training
permission. Optional `X-Omi-Firmware-Version`, `X-Omi-Device-Model`, and existing
`X-App-Version` carry upload provenance. Live sockets accept the corresponding
headers and `X-Omi-Audio-Consent-Version`. Auto-assigned sync archives carry
`sync_job_id` and append completed `conversation_ids` under the owner fence;
a multi-conversation original has no invented singular owner link.
Enhanced protection encrypts unchanged canonical bytes. PCM captures use FLAC;
playback resampling is a rendition operation only.

## Lead provisioning (do not run in tests)

Choose an environment-owned regional bucket in the **customer data project**;
do not substitute the compute project's identity/data plane. Example placeholders:

```sh
source ~/.local/bin/gcp-agent-env.sh prod-operator
export AUDIO_DERIVED_BUCKET='<approved-regional-bucket>'
gcloud storage buckets create "gs://${AUDIO_DERIVED_BUCKET}" \
  --project=based-hardware --location=us-central1 \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update "gs://${AUDIO_DERIVED_BUCKET}" --clear-soft-delete
gcloud storage buckets update "gs://${AUDIO_DERIVED_BUCKET}" --no-versioning
```

Grant the existing customer-data runtime identity object access, through the
approved IAM path. Set `BUCKET_AUDIO_DERIVED` on all readers/writers/deletion
workers before enabling the cache cohort. Apply lifecycle expiry only to
`merged/` (3 days), `playback/` (30 days), and `syncing/` (1 day). Sync rendition
`chunks/` must remain available until a qualified original-file playback adapter
can regenerate it; do not add a deletion TTL to that prefix in this trial.
Do not change canonical lifecycle/retention policy. Existing legacy staging's
seven-day soft-delete residue cannot be purged early; deletion verification must
report it separately rather than claiming physical erasure.

Merge and STT already have distinct Cloud Tasks job classes (`audio-merge`,
`sync-jobs`) and distributed job leases. An independently sized merge service
may reuse the same GitHub-built immutable backend image and customer-data
identity, with authenticated Cloud Run ingress, the merge queue's existing
invoker SA and its endpoint-specific OIDC audience. Configure
`AUDIO_MERGE_WORKER_URL` on enqueue and consumer services, then test a single
named task before the cohort ramp. Do not enable a worker without runtime-image,
identity, index-readiness and route qualification.

First deploy this SHA at the default 8Gi through GitHub Actions. For the
separate memory trial, the lead creates a tagged **no-traffic** 6Gi revision
from that already-built same-SHA image, routes at most 5% to it and waits ≥12h.
Only after qualification/full promotion set GitHub environment variable
`BACKEND_SYNC_MEMORY=6Gi` for future deployments; the backend-stack action validates only `6Gi|8Gi` and defaults
to `8Gi`. The deployment remains through the existing release admission and
GitHub Actions workflow. Rollback: restore `8Gi`, redeploy the admitted image.
Watch memory peak, OOMs, queue age and retry rate; 4.9 GiB is an observed sample
peak, not qualification for the largest batch.

## Cost model and receipt

C023 October 7–11 baseline: **$173.12/day**, 4.223M billed instance-seconds,
2 CPU/8 GiB. Planning after adoption is ~$170/day; proven savings are zero.
Do not multiply the sampled 90% merge HTTP-time share by the full bill.

| Lever | Expected/modelled daily saving |
| --- | --- |
| 8→6 GiB | About **$13/day** net at unchanged billed seconds; unqualified at batch peaks. |
| Rebuild coalescing | `$173.12 × duplicate billable fraction removed`; fraction unmeasured, conservative booked value **$0/day**. Counter measures calls, not billed seconds. |
| Separate merge job class/worker | Direct separation alone **$0/day**; ideal combined CPU packing to 60% models **$38–58/day** across this and coalescing, not additive per-lever savings. |
| GPU callbacks | **$0/day implemented/credited**. Current Parakeet `/v1/transcribe` and `/v2/transcribe` return inline results and have no durable submission/result callback contract. Async HTTP alone still bills Cloud Run waits. A durable idempotent GPU job/result store and authenticated callback are prerequisite; do not acknowledge sync completion before that result is checkpointed. |

GCS measured baseline: replication **$54.89/day**, Class A **$65.82/day**
(all buckets); main audio shares $49.57/$50.46. Raw 13.2 vs PCM 115.2 MB/hour
is a synthetic format experiment (88.5% smaller), not a fleet bitrate or daily
savings forecast. Regional cache writes avoid new multi-region replication.
Bounded/hour-pack final writes do not erase initial PCM PUTs in dual-write or
initial fragment PUTs; never book the proposed 60→1 PUT saving before observing
actual object counts. At-rest storage is excluded from the worn-hour receipt.

Prometheus: `omi_audio_archive_objects_total{source,codec}`,
`omi_audio_archive_bytes_total{source,codec}`,
`omi_audio_archive_pcm_writes_avoided_total`,
`omi_audio_archive_rebuilds_coalesced_total`; failures use shared
`omi_fallback_total`. Compare closed-day billing replication/Class A/Class B,
backend-sync instance-seconds, memory, retries and completed worn-hours with the
same 7-day baseline. These counters are operation evidence, not billing dollars.

## Qualification and rollout

1. Hermetic replay: `printf '%s\n' tests/unit/test_sync_ingest_archive.py tests/unit/test_mobile_standard_batch.py tests/unit/test_owner_storage_purge_and_gate.py tests/unit/test_audio_merge_tasks.py > /tmp/archive-tests.txt`; run `BACKEND_UNIT_TEST_FILE_LIST=/tmp/archive-tests.txt bash backend/test.sh` (macOS native Opus also needs `DYLD_LIBRARY_PATH=/opt/homebrew/lib`). No test calls live Firestore or production APIs.
2. David's canary: client WAL/container SHA-256 must equal canonical metadata and downloaded bytes for standard protection. `sha256sum <client-wal> <downloaded-object>`; download with `gcloud storage cp "gs://<canonical>/<canary-object>" <local-file>`. Enhanced protection compares decrypted plaintext inside the authorized harness, never prints keys. Compare packet list and decoded sample count too; PCM compares lossless FLAC samples.
3. Use the lead's owned capture/playback harness for one raw-only conversation: measure cold/warm playback first-byte and complete latency, duration, gaps and duplicate ranges, and a successful batch final pass. No ad hoc authenticated `api.omi.me` user calls.
4. Delete that canary account through the supported product flow. Read-only verification: `gcloud storage ls --all-versions "gs://<canonical>/raw-live/<uid>/**"` and equivalent `raw-sync/`, `raw-mobile-batch/`, `chunks/`, `audio/`, `merged/`, `playback/`, `syncing/` in every configured bucket. Expect no live or noncurrent objects. Report any pre-existing soft-deleted residue separately.
5. Measure bytes/worn-hour and retirement coverage. Target ~13 MB only after phase C demonstrably suppresses the full ~115 MB live PCM stream; hold the ramp if committed coverage, provenance, playback or deletion fails. Read replication/Class A deltas from the closed billing day, not counters alone.
6. For **each** independent phase: David → at most 5% → wait at least 12h with gates green → all. Roll back its enable to false (STOP_PCM first; retain READ for raw-only history), retain bucket URLs, and verify fresh sessions again. No rollout or deployment was executed by this PR.

Conversation deletion also purges linked originals (including a shared multi-conversation upload),
raw-live packs, chunks, merged and playback objects in both buckets and all generations.
Missing regional/worker destinations log and retain the existing bucket/handler.
Consent-off mobile uploads are accepted without cloud archival.

## Coexistence with verified owner packs (#21544)

The independent `AUDIO_CANONICAL_PACKING_ENABLED`/`BUCKET_CANONICAL_AUDIO`
forward archive remains intact. `merged_into` links owner packs before donor
cleanup; a failed link aborts cleanup. Mobile forwarding follows a successful
primary raw commit and remains best-effort. Proven PCM retirement still invokes
the optional owner-pack writer. If both archive systems are enabled, count those
forward PCM bytes in the receipt: the ~13 MB/worn-hour target applies to this
live raw/PCM leg and must not be claimed for total storage across both systems.
