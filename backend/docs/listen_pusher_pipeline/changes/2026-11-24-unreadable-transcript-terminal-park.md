# Park an unreadable stored transcript instead of retrying it

A confirmed decode failure on the stored transcript is now a permanent classification, not a pending
first summary (SCA-4178). SCA-3874 made sync finalization stop rather than discard an undecryptable
transcript, but it signalled that stop as `FirstSummaryCallbackPending`, so every delivery answered 409
`callback_pending` and the queue retried until the 72 h age gate. The Go replay oracle
(`unreadable-ciphertext-dead-letters`) measured 868 deliveries and 13,890 Firestore operations for one
conversation.

`require_transcript_decoded` now raises `utils.enrichment.outbox.TranscriptUnreadable`. Both enrichment
handlers settle it on the first delivery:

- the push consumer (`/v2/enrichment/run`, `/v2/sync-jobs/run` with `ENRICHMENT_ROUTE=enrichment_queue`)
  answers `200 discarded transcript_unreadable`; `ack` retains the obligation dormant with
  `held_reason=transcript_unreadable` and `held_at`;
- the legacy batch/finalization binding's `outbox.run` helper returns `held` and parks the same shape.

Nothing else changes. The conversation row is never written: the stored ciphertext, `transcript_segments`
and `transcript_segments_compressed` stay byte-for-byte, any previously delivered summary stays, and no
provider, claim or `process_conversation` step runs. A Cloud Tasks redelivery of the parked row claims as
stale and costs two reads. The existing `omi_sync_finalization_transcript_decode_failure_total` still
counts one failure per attempt, and the consumer result counter carries the new
`reason=transcript_unreadable` (the legacy binding also records `omi_fallback_total` with that reason).

Readers of the terminal state:

- the outbox sweep: a dormant row has no `due_at`, so it is never re-woken;
- `summary_debt_repair.redrive`: refuses a terminal hold, like the v3 custody receipt, so the repair tick
  cannot restart the same delivery;
- `utils.enrichment.redrive` (operator re-wake): a dormant row already answers `settled`;
- `database.conversation_parked_status` (SCA-3590 status migration): the retained outbox row still fences
  the conversation, so nothing flips its status;
- `outbox.mark` / `mark_update`: a new content revision reopens the row and clears `held_reason`/`held_at`,
  so a re-upload or key fix is classified again. This is the only recovery path; the park is terminal by
  ruling, not an undeleted retry loop.

The age gate is unchanged and still handles rows that never reach a claim. Contract:
[enrichment age gate](../../runbooks/enrichment-age-gate.md).
Hermetic coverage: `tests/unit/test_enrichment_route.py`. Emulator coverage:
`tests/integration/test_enrichment_unreadable_transcript_firestore.py` (one delivery parks, 40 Firestore
operations for the park plus its stale redelivery) and
`tests/integration/test_summary_debt_repair_firestore.py`.
