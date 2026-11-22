# 2026-11-21 Historical V3 partition limits

Historical sit-down repair plans up to 384 range documents per partition and
loads up to 400. Its range plus closure budget is 512 reads per partition,
including missing point reads. Deleted claimants still fence speech. The
planner preserves the 900-second silence seam and 3,600-second landing lock.
The existing limits still apply to ordinary derive and live re-derive.

The historical loader streams snapshots and separately caps the estimated
stored payload, expanded codec input, and hydrated payload at 16 MiB each.
Compressed data and lake transcripts apply the expansion budget before
decoding. Overflow stops the partition. The preview reports a model-free
write estimate. Apply still checks the actual plan against existing custody,
commit write-count, document-size, and transaction-size limits.

Historical re-derive may use the exact Firestore update time of a sealed,
completed legacy source that lacks a landing field. The revision must be at
or after the decoded speech end and at least 3,600 seconds old. A stretch with
uncertain legacy landing stays protected. An outer edge with uncertain context
protects the entire connected stretch and its claimants. Unresolved edge
closure aborts planning. Bounded decoding distinguishes an empty compressed
correction history from edited or unreadable data.

## Rollout and rollback

The larger limits apply only to explicit historical sit-down runs. Keep the
Lab reader's approved cumulative Firestore and object-read counters in place.
Pause dispatch before sending plans made with these limits to older workers.
Use the existing undo flow for an applied repair when its custody checks permit it.

## Verification

The [live re-derive tests](../../../tests/unit/test_conversations_v3_live_rederive.py)
cover a synthetic 352-document stretch, deleted claimant closure, overflow,
seam validation and the historical apply write guard. The
[lake tests](../../../tests/unit/test_object_lake.py) cover bounded downloads
and expansion.

[Backfill and repair runbook](../../runbooks/conversations-v3.md#backfill-and-repair-per-owner)
