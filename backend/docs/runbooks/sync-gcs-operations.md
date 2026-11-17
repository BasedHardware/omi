# Private sync GCS read operations

`50ac51ce18cd0046206eb03e905cdecb1deb5156` added decoded original recovery after
successful relay sends could leave capture unconsumed. The proof is required:
metadata alone never authorizes projection, a custody ACK, source deletion,
a producer-token clear or a record seal. See the
[recovery contract](../listen_pusher_pipeline/changes/2026-11-16-pusher-gap-recovery.md).

The read optimization preserves consent/deletion preflight, commit-time privacy
and audio_files CAS, owner/hash/frame checks, 20-second discovery deadlines,
64 new decodes, 16 MiB stored packs, 128 MiB decoded bytes and 4096 frame/index
bounds. No PCM is retained by a new cache.

## What is reused

- A loaded blob with metadata, size, generation and metageneration can replace
  a reload. Downloads pin **both** generations; a changed/missing object raises.
  Unknown metadata still requires a GET (including bare path/receipt reads that
  cannot yet know encryption or stored-byte bounds). Hash, decrypt and decode
  checks still run.
- A rebuild keeps bounded manifest **metadata**, not manifest bodies or PCM.
  Every use still downloads and validates the pinned manifest body. Gapped
  manifest listings already supply metadata, so their reload is redundant.
- Each CAS attempt still reads current media metadata. Its generation,
  metageneration, media hash and validated frame digest key the decode proof.
  A rebuild retains that proof even if another reader evicts the process cache;
  unchanged packs decode once within the existing proof-count bound. The local
  cache holds only proof keys and expiry times, never frame arrays or PCM. Changes require a new proof or fail closed.
  A backend without metageneration cannot reuse decode proof.
- Strict raw listings are reusable only if complete, unexpired (120 seconds),
  started within the current rebuild, within its object-scan/entry limits, and
  taken with the same gapped-pack setting. Local writes still invalidate them.
  A retry re-reads encoded inventory and the conversation CAS snapshot.

An older per-instance index cannot prove it is newer than the write that
triggered repair: current rebuild callers pass no trusted write timestamp.
Therefore the first raw listing remains fresh. Cross-rebuild strict reuse is
intentionally excluded. Required-archive replay also retains `fresh=True`.
Gapped-manifest uniqueness listings remain: cached evidence cannot hide a new
ambiguous manifest. Failed reads retain debt and originals.

## Operations from code and synthetic execution

Counts below are logical GCS calls, for one uncovered pack with metageneration,
a cold decode-proof cache, no retries, and one LIST page per prefix. Baseline is
`9798014f4ac018fcbdf01a99d7b25a5e8668c2cf`. The two-attempt case forces an
`AudioFilesChanged` CAS conflict; unchanged metadata permits proof reuse.

| Rebuild | LIST before → after | Metadata GET before → after | Body read before → after |
| --- | --- | --- | --- |
| Framed, one attempt | 1 → 1 | 4 → 2 | 3 → 3 |
| Framed, two attempts | 2 → 1 | 7 → 3 | 5 → 4 |
| Gapped unframed, one attempt | 3 → 3 | 4 → 1 | 3 → 3 |
| Gapped unframed, two attempts | 6 → 4 | 7 → 2 | 5 → 4 |

After inventory, **validation itself goes from 3 metadata GETs to 1** per fresh
pack proof. Its two body reads remain: one manifest and one media object.
Initial framed inventory additionally needs one manifest GET/read; gapped
inventory gets metadata from its manifest listing. Those costs are included
in the table, not hidden. Each already-loaded pack/manifest read removes one
metadata GET and still downloads the body with generation preconditions.
A path without loaded metadata retains its required GET.

The process proof cache already avoided many repeated decodes before this
change. The new rebuild-local proof guarantees that property during a CAS retry
even after process-cache eviction; it does not claim every rebuild formerly
decoded twice. New or changed packs still pay for validation.

## Counter and rollback

`omi_sync_audio_gcs_operations_total{scope="rebuild|read",operation="rebuild|list|metadata|read"}`
counts logical call attempts, including failures. `scope="rebuild"` covers
original inventory/validation inside a privacy-qualified rebuild; encoded chunk
listing, Firestore work, other storage paths, SDK LIST pagination and transport
retries are outside this counter. It is not a billing meter. `rebuild` is one
denominator increment per invocation, including both CAS attempts. Both Cloud
Run collector profiles retain this metric; tests also check later drop rules.

Operations per rebuild, separated by kind:

```promql
sum by (operation) (rate(omi_sync_audio_gcs_operations_total{scope="rebuild",operation=~"list|metadata|read"}[1h]))
/
ignoring(operation) group_left
sum(rate(omi_sync_audio_gcs_operations_total{scope="rebuild",operation="rebuild"}[1h]))
```

Listing reuse is on unless `SYNC_GCS_REBUILD_LISTING_REUSE_ENABLED=0`, `false` or
`off`. One-line rollback of listing reuse: set
`SYNC_GCS_REBUILD_LISTING_REUSE_ENABLED=off` on the owning repair/read services
through their normal reviewed release/config path. This forces a fresh raw
listing on each attempt; version pinning and metadata/decode reuse remain.
Revert the PR to roll back the complete optimization.

No deploy or production config change is performed by this PR. Compare equal
traffic windows after release, alongside proof failures, repair debt/age and
playback errors. No saving is claimed.
