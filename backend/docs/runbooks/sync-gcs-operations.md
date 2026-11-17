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
Every CAS attempt takes a new strict raw LIST **after that attempt's conversation
snapshot**, including retries. A peer commit can add original packs before the
retry's snapshot; reusing an earlier inventory could overwrite their projection
coverage while passing CAS. Strict listing reuse and its kill switch are removed.
Ordinary non-strict playback retains its existing 120-second per-instance cache;
required-archive replay retains `fresh=True`.
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
| Framed, two attempts | 2 → 2 | 7 → 3 | 5 → 5 |
| Gapped unframed, one attempt | 3 → 3 | 4 → 1 | 3 → 3 |
| Gapped unframed, two attempts | 6 → 6 | 7 → 2 | 5 → 5 |

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

Operations per rebuild, separated by kind, **queried directly against GMP**
(for example with the read-only `tools/gmpq.sh '<PromQL>'` helper). This family is
kept by the Cloud Run GMP collectors but is not imported by the in-cluster
`prometheus-stackdriver-exporter` allowlist. The query therefore works in GMP,
not against the in-cluster Prometheus datasource. No exporter import is added
because no in-cluster dashboard depends on this new counter:

```promql
sum by (operation) (rate(omi_sync_audio_gcs_operations_total{scope="rebuild",operation=~"list|metadata|read"}[1h]))
/
ignoring(operation) group_left
sum(rate(omi_sync_audio_gcs_operations_total{scope="rebuild",operation="rebuild"}[1h]))
```

Rollback: revert this PR and release the revert through the normal reviewed
release path. There is no listing-reuse switch; every strict attempt always
re-lists. A manifest generation mismatch excludes only that pack during ordinary
non-strict playback discovery; strict recovery still raises and retains debt.

No deploy or production config change is performed by this PR. Compare equal
traffic windows after release, alongside proof failures, repair debt/age and
playback errors. No saving is claimed.
