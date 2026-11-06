# Transcript lake codec (C2)

Oversized `transcript_segments` can now become a `LakeObjectRef` dictionary in the
same stored field. The API still returns a segment list. This applies to the
shared conversation codec used by backend, backend-listen, backend-sync,
pusher, and the separately released desktop-backend. Sibling JSON fields and
the recurring-voice scrub continue to write inline.

`OBJECT_LAKE_WRITE_ENABLED=false` and `OBJECT_LAKE_WRITE_PERCENT=0` remain the
admission defaults. With admission closed, encoding is byte-identical to the
previous JSON/zlib (and enhanced encryption) codec. O1 keeps production writing
off until C4's wipe-coverage test passes. Dev qualification precedes the ramp
already recorded in the [feature flag registry](../../feature-flag-registry.md).
Redeploy every reader, including desktop-backend, before admitting pointers.

A put precedes the document write that references it. Transactional reads choose
the pointer from their own snapshot; cold references abort the attempt, preload
outside Firestore, and retry with a bounded plaintext memo. The full reference
and digest identify memo entries. The retry boundary admits at most 32 distinct
conversation preloads plus three content changes, with 36 total attempts and
superseded versions evicted before preloading their replacement. Finalization
admission, empty-recording deletion, sync candidate/canonical selection, voice
publication, and episode memo/timeline owners all use this boundary. Missing
objects are filtered from list/MCP results; transport failures abort decisions.
Transactional encodes stay inline and queue a
post-commit upload and update-time CAS; live `in_progress` rows are skipped.
Failed swaps retain readable inline data. Orphan cleanup belongs to C3.

Lake transport/key availability failures raise `TranscriptPointerFetchError`;
they never become empty speech or ciphertext. An absent blob denotes a deleted
conversation. Destroyed keys raise the distinct `TranscriptShredded` state;
transactional domain operations refuse them as unavailable. Corruption retains
the strict decoder's existing error. Turning lake reads off fails closed even
on warm memo entries. The bounded public-chat decoder remains inline-only, so
pointer documents are excluded from public-chat candidates.

Space-key destruction now retains a content-free tombstone, including for an
owner without any prior key. It blocks future get-or-create operations and
puts check the durable customer-plane account-deletion marker before key creation
and again after upload, cleaning up late objects. An unavailable marker fails closed. C4 must
preserve that tombstone, fence owner mutations, quiesce in-flight puts, purge the
prefix, and destroy keys last. This PR does not integrate or run an account wipe.
Wrapped-key corruption remains unavailable/retryable rather than shredded. Each
unwrap reads key authority once; each put reads it twice (before encryption and
after upload), including retries, plus two uncached account-deletion marker reads per put. KMS work alone is cached across operations.
Transcript plaintext expansion is capped at 32 MiB; future data classes need an
explicit size limit before admission. No env bindings or migrations are added.

Evidence: [codec/transaction mechanics](../../../tests/unit/test_transcript_pointer.py),
[reader/domain/fence contracts](../../../tests/unit/test_conversation_transcript_offload.py),
and [key lifecycle](../../../tests/unit/test_space_keys.py). The implementation
result records exact local test commands and any unverified acceptance criteria;
local hermetic results do not claim a deployed or provider-backed round trip.
