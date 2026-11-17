# Private sync GCS read operations

`50ac51ce18cd0046206eb03e905cdecb1deb5156` added decoded original recovery after
successful relay sends could leave capture unconsumed. Metadata alone never
authorizes projection, a custody ACK, deletion, a token clear or a record seal.
See the [recovery contract](../listen_pusher_pipeline/changes/2026-11-16-pusher-gap-recovery.md).

## Restricted scope

Only remove a metadata reload when the caller already fetched that same object's
metadata in the current call chain: the fresh validation GET supplies the media
blob to decoding, and fresh gapped-manifest listings supply their manifest blob.
Downloads pin generation **and metageneration**. Unknown metadata still gets a
GET. Hash, encryption, frame, size, privacy and CAS checks remain.

There is no new metadata, manifest, listing or decode-proof cache. Each strict
attempt snapshots the conversation, re-lists and reads live media and manifest
metadata as main does. Metadata is never retained for a subsequent attempt or
call. Main's existing process decode-proof cache is unchanged, including the
fresh metadata/manifest checks before using it and decoding again after eviction.
Main's existing two-field, 120-second non-strict index cache and its behaviour
are restored exactly; cache eligibility, bounds and flag semantics are not changed
by this PR. Required-archive and strict recovery remain fresh. The ContextVar
holds only a boolean for counter labels, never read or validation state.

A generation mismatch excludes only the affected pack during non-strict listing;
strict recovery raises. Failures retain originals and recovery debt. No new flag
is introduced. Rollback is a normal reviewed revert and release of this PR.

## Per-attempt metadata GETs

Counts are per uncovered pack, one LIST page per prefix, against main baseline
`9798014f4ac018fcbdf01a99d7b25a5e8668c2cf`. Inventory and validation are separate:
framed inventory still GETs its manifest; validation GETs that manifest again.
Those reads are deliberately not shared, even within one attempt.

| Pack / main proof cache | Inventory before → after | Validation before → after | Total before → after | GETs removed |
| --- | --- | --- | --- | --- |
| Framed, cold/miss | 1 → 1 | 3 → 2 | 4 → 3 | 1 |
| Framed, warm/hit | 1 → 1 | 2 → 2 | 3 → 3 | 0 |
| Gapped unframed, cold/miss | 1 → 0 | 3 → 1 | 4 → 1 | 3 |
| Gapped unframed, warm/hit | 1 → 0 | 2 → 1 | 3 → 1 | 2 |

A fresh framed proof removes only the decode-time media reload. A gapped pack
also removes two manifest reloads whose metadata is already in that call's LIST
results. A warm main proof avoids decoding already, so framed warm hits save no
GETs. An already-loaded individual pack/manifest read removes one GET; bare path
reads retain their GET. LIST and body-read counts are unchanged.

| Rebuild, initially cold main proof cache | LIST before → after | Metadata GET before → after | Body read before → after |
| --- | --- | --- | --- |
| Framed, one attempt | 1 → 1 | 4 → 3 | 3 → 3 |
| Framed, two attempts, unchanged proof retained by main | 2 → 2 | 7 → 6 | 5 → 5 |
| Gapped unframed, one attempt | 3 → 3 | 4 → 1 | 3 → 3 |
| Gapped unframed, two attempts, unchanged proof retained by main | 6 → 6 | 7 → 2 | 5 → 5 |

If the existing proof is evicted before retry, both main and this change decode
again: framed two-attempt GETs are 8 → 6, gapped GETs are 8 → 2, and body reads
are 6 → 6. No new cache tries to preserve a proof across retries.

The strict requirement of at least one GET removed **for every pack on every
attempt is not met**: a framed warm proof hit removes zero. Under that threshold,
recommend closing the PR rather than adding more reuse. Runtime mix and savings
are not established. No saving is claimed.

## Counter query

`omi_sync_audio_gcs_operations_total{scope="rebuild|read",operation="rebuild|list|metadata|read"}`
counts logical calls, including failures. `scope="rebuild"` covers raw inventory
and validation inside a privacy-qualified rebuild. Encoded chunk LISTs, Firestore,
other storage, LIST pagination and SDK transport retries are outside this counter.
The rebuild denominator increments once per invocation, including both attempts.
It is an application counter, not a billing meter.

Query directly against a **GMP PromQL datasource**. Both Cloud Run collectors
retain the family; it is not imported by the in-cluster Stackdriver exporter.
Operations per rebuild, separated by kind:

```promql
sum by (operation) (rate(omi_sync_audio_gcs_operations_total{scope="rebuild",operation=~"list|metadata|read"}[1h]))
/
ignoring(operation) group_left
(sum(rate(omi_sync_audio_gcs_operations_total{scope="rebuild",operation="rebuild"}[1h])) > 0)
```

The denominator comparison intentionally omits `bool`: a positive rate retains
its value; a zero or absent denominator produces no result instead of infinity.
No helper script is assumed. No in-cluster exporter import or production change
is included. This PR performs no deploy or production config change.
