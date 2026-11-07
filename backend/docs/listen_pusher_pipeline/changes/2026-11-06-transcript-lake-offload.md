# Transcript lake codec (C2)

Oversized `transcript_segments` can now become a `LakeObjectRef` dictionary in the
same stored field. The API still returns a segment list. This applies to the
shared conversation codec used by backend, backend-listen, backend-sync,
pusher, and the separately released desktop-backend. Sibling JSON fields and
the recurring-voice scrub continue to write inline.

`OBJECT_LAKE_WRITE_ENABLED=false` and `OBJECT_LAKE_WRITE_PERCENT=0` remain the
admission defaults. With admission closed, encoding is byte-identical to the
previous JSON/zlib (and enhanced encryption) codec. O1 keeps production writing
off until C4's wipe-coverage test passes. The merge-owner crypto fence also
blocks writes outside explicit local/offline stages until per-object DEKs land;
neither a provisioned KMS key nor either write flag can bypass it. Both runtime
and deploy validation enforce this prerequisite before the ramp recorded in the
[feature flag registry](../../feature-flag-registry.md).
Redeploy every reader, including desktop-backend, before admitting pointers.

A put precedes the document write that references it. Transactional reads choose
the pointer from their own snapshot; cold references abort the attempt, preload
outside Firestore, and retry with a bounded plaintext memo. The full reference
and digest identify memo entries. The retry boundary admits at most 32 distinct
conversation preloads and 32 candidate uploads, plus three content changes
across reads/uploads, with 68 total attempts. Superseded read versions are evicted before
preloading their replacement. The decoded memo holds at most 32 entries and
64 MiB of decoded Python containers/strings; exceeding the byte budget raises
retryable `TranscriptMemoBudgetExceeded` instead of silently evicting required
content. Plaintext expires after 120 seconds and is cleared at operation end. Finalization
admission, empty-recording deletion, sync candidate/canonical selection, voice
publication, and episode memo/timeline owners all use this boundary. Missing
objects are filtered from list/MCP results; transport failures abort decisions.
Admitted transactional encodes above the compressed inline threshold abort
before staging the transcript write. The boundary uploads the candidate outside
Firestore, then reruns the entire transaction from a fresh snapshot. Only the
exact recomputed source digest may use that pointer. Retry identity is computed
before randomized grouping-sidecar protection; the pointer hash still authenticates
the actual protected JSON uploaded to the lake. Invalid optional grouping evidence
retains its existing drop behavior, using a streamed typed fingerprint without
copying the transcript tree. Transaction candidates do not warm existing-pointer
reads; those still preload from the lake. Direct pre-transaction encodes cache
the actual upload JSON, never a later encryption of the same source. This includes live
`in_progress` rows, whose transcript may already exceed Firestore's 1 MiB limit.
The C3 backfill primitive still uses an update-time CAS and skips live rows;
failed backfill swaps retain readable inline data. Orphan cleanup belongs to C3.
Normal writes and backfill share the same privacy gate: only explicitly shared
or public, non-deleted, unlocked rows may offload; private/unknown visibility
stays inline. Partial writes consult the stored policy as well as the payload.
Lifecycle decorators encode inline until the transaction passes its current-row
guards and recurring-voice privacy filter, then request a candidate through the
preupload/replay boundary. Refused deleted/stale/missing-owner writes and existing
create-if-absent rows never upload before those guards.
Missing bucket or release bindings close write admission; unset KMS deliberately
selects the existing offline FakeKMS. Production write admission stays off under O1.

Lake transport/key availability failures raise `TranscriptPointerFetchError`;
they never become empty speech or ciphertext. An absent blob denotes a deleted
conversation. Destroyed keys raise the distinct `TranscriptShredded` state;
transactional domain operations refuse them as unavailable. An absent/shredded
transcript removes only the transcript content signal: photos and the durable
`has_content` marker still prevent empty-recording deletion. Every dictionary,
including an empty malformed pointer, passes strict validation and therefore
counts as unreadable content rather than an empty recording. Corruption retains
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

`object_lake.verify_space_object(ref, deep=True)` returns `False` for a destroyed
key and propagates `SpaceKeyUnavailable` for a temporarily unavailable key.
Shallow verification can still return `True` in both cases: it checks stored
metadata/size, not decryptability. Consumers needing the distinct shredded state
must use the transcript decoder; a deep-verify `False` alone is not proof that
the object is absent and must never authorize deletion.

Evidence: [codec/transaction mechanics](../../../tests/unit/test_transcript_pointer.py),
[reader/domain/fence contracts](../../../tests/unit/test_conversation_transcript_offload.py),
and [key lifecycle](../../../tests/unit/test_space_keys.py). The implementation
result records exact local test commands and any unverified acceptance criteria;
local hermetic results do not claim a deployed or provider-backed round trip.
