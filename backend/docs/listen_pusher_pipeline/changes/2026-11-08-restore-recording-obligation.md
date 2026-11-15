# Restore sealed recording obligations

Explicit restoration of a sealed `batch_live_v1` capture now registers its
recording obligation even when the discarded finalizer already committed a
terminal fanout fence. The lifecycle wrapper uses the metadata transaction's
snapshot to select the capture, then re-reads the row in the canonical recording
registration transaction. A second discard, deletion, ownership change or
privacy refusal cannot create an obligation from that stale snapshot.

Registration keeps its deterministic recording identity, privacy generation and
commit fence. Refusal raises a retryable lifecycle error; reprocess responds
with HTTP 503 and `Retry-After`. A retry of the persisted user-kept row attempts
registration again. No scan, repair discovery or rollout flag changes.

Hermetic coverage in `test_restore_recording_obligation.py` checks idempotence,
post-restore fences, privacy refusal, retry and HTTP error propagation. These
are local lifecycle guarantees, not deployment evidence. See the
[recording pipeline contract](../../listen_pusher_pipeline.mdx).
