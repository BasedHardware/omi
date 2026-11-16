# Exact native-record WAL custody, phase 1

The [native record WAL custody contract](../../listen_pusher_pipeline.mdx#native-record-wal-custody-handoff-phase-1)
replaces repeated strict PCM coverage refusals with an exact original-byte
handoff under the existing owner. Independently decoded Opus files and native
PCM cannot generally compare byte-for-byte, and phone WALs can include frames
never sent live. This phase keeps every submitted original durable and leaves
its processing obligation pending; it does not plan gaps or dispatch paid STT.

Bundle receipts and stable per-file receipt rows use the existing stage-qualified
intake collection, with explicit kinds. Each file row carries its pending
obligation and outbox wake atomically; `wal_pending_since` provides indexed
discovery. Ordinary job dispatch never consumes them.

`RECORD_WAL_HANDOFF_ENABLED` is a **default-off `config_switch`**. Unset, false,
0, off, no and unknown values keep admission off, including intervening main or
image-only deployments. Accepted receipts, headerless status readers and erasure
remain live with admission off. Only true/1/on/yes admit new handoffs.

Release owns this proposed rollout; the quality lead reviews its evidence. No
activation or deployment is authorized by this PR:

1. **2026-11-16 UTC:** deploy this receipt-capable artifact everywhere with
   admission off, including every sync/status and erasure-serving revision.
   Verify image/source identity and Cloud Run **`status.traffic`**, not the
   service spec: every revision receiving sync/status traffic must be capable.
   Complete synthetic staging custody, headerless polling and conversation/
   account erasure checks. Leave admission off if any serving reader is old.
2. **2026-11-17 UTC, only after step 1:** the existing release owner sets
   `RECORD_WAL_HANDOFF_ENABLED=true` on **backend-sync only**, using a revision
   of the same artifact. Start with synthetic staging/internal test capture,
   then ramp **1%, 10%, 50%, 100% of backend-sync traffic** against the capable
   admission-off base. Each step requires a full clean 60-minute lookback;
   quality lead reviews before expansion. Finish or explicitly stop the ramp
   by **2026-11-18 00:00 UTC**; no automatic expansion or flag promotion.
3. Every step requires **custody violations = 0** (no 202 without all bytes,
   no missing known handle, no premature completed status), no unexpected paid
   work, fresh pending samples, pending bytes below 80% of the 4 GiB global
   cap and oldest pending age below 6 hours. Sync 5xx must not increase over
   the preceding admission-off 60-minute baseline. Watch pending file counts,
   `omi_record_wal_handoff_pending_bytes`, `oldest_age_seconds`,
   `sampled_at_seconds`, fixed-scope `capacity_refusals_total{scope=owner|global}`
   and sync 5xx. A capacity refusal keeps phone custody but stops expansion.
   Stop new admission immediately on a custody/status/erasure violation,
   stale metrics, 5xx regression or an age/volume breach. By **2026-11-18 UTC**
   Release and the quality lead review every outstanding hold; any oldest age
   reaching 24 hours requires admission off and a phase-2 recovery plan.

Rollback sets admission false and retains receipt-capable readers and erasure
at 100% traffic. It never routes known handles to an incapable binary. A capable
revision handles the released app's ordinary headerless status request directly
from Firestore, independently of ordinary jobstore shadow/index adapters.
An incapable revision cannot interpret `bp_wh_`: it can return 404/unknown-job,
or a legacy reader that treats the receipt as an ordinary intake can error
(500 on missing ordinary-job fields). Neither is a valid processing response;
this is why the traffic proof must precede the first admission.

Capacity is reserved atomically **before the first object write**, once per
stable original file. The per-owner defaults are **256 MiB (268,435,456 bytes)**
and **200 files**; the global defaults are **4 GiB (4,294,967,296 bytes)** and
**10,000 files**. Both stage namespaces share the global and owner ledgers in
the existing production intake collection. Limits are configurable through
`RECORD_WAL_PENDING_OWNER_BYTES`, `RECORD_WAL_PENDING_OWNER_FILES`,
`RECORD_WAL_PENDING_GLOBAL_BYTES`, and `RECORD_WAL_PENDING_GLOBAL_FILES`.
Zero closes new capacity; negative values close it and malformed values refuse
safely. Bytes conservatively include the original length plus 32 bytes for the
current encryption envelope, even for standard protection.

An exceeded owner or global cap returns the existing strict
`record_capture_pending` 503 before copying any file; the fixed-scope capacity
counter increments and the phone keeps its audio. Exact retries and rebundles
reuse reservations. Object-only crashes remain charged, without expiry, so a
fresh nonce or interrupted write cannot bypass the bound. Media erasure must
succeed before its reservation and counters are released atomically. Failed
attempts can consume capacity until explicit privacy erasure; phase 1 has no
unsafe timer-based reclaim. Pending bytes include these conservative holds.

Account and conversation erasure sweep **every generation** of the exact
`record-wal/{uid}/{conversation_id}/` prefix (or the owner prefix for account
purge), including crash orphans, before metadata/quota cleanup. The handoff's
sole write target is the configured `BUCKET_PRIVATE_CLOUD_SYNC` archive bucket;
both purge paths derive that same target. The resumable conversation purge
uses bounded pages and its existing gated, generation-pinned remote deletion
units, re-lists after restart, and cannot acknowledge a failed/unknown erase.
No historical bucket migration or live bucket policy has been verified here.

Phase 2 adds proven source-frame overlap/gap planning, original/in-flight
coverage seeding, same-owner interval reservations and projection, and terminal
status only after every original's obligation settles. Phase 1 improves custody
and upload status; it makes no claim of recovered transcript or paid deduplication.
