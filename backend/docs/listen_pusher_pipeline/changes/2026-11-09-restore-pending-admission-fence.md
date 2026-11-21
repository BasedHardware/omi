# Restore-only pending metadata fence

Recording restore registers its durable obligation before committing visibility
metadata. If that metadata transaction fails, the conversation stays discarded
and the obligation stays retryable. Admission reads the conversation and the
relevant jobs inside its transaction on every record path, including full
archives, partial children, and ledger replay. It refuses admission with the
existing retryable error when the discarded row has a
`registration_origin == 'restore'` job being admitted or canonical recording
obligation. Main's existing `(partial_parent and row.get('discarded'))`
refusal is preserved independently: a discarded partial-parent continuation
is refused even without a pending restore. Deleted, missing, and custom-STT
targets retain their refusals.

Ordinary non-partial jobs on automatically discarded conversations retain main's
admission behavior. Later speech replacement clears an ordinary automatic discard and its
old relevance verdict so enrichment can reassess it. Replacement rereads the
canonical recording obligation in the assignment transaction: a restore-pending
row keeps its discard and verdict until `restore_conversation_from_discarded`
commits the user's metadata. User discards remain protected.

This ships on with no new flag. Risk: restore-origin obligations remain retryable
and parked when metadata cannot commit; this change does not repair or cancel
them. Rollback: revert the PR. Deployment belongs to the lead's backend image
train and affected sync/projection hosts after review and merge.

Regression coverage: `tests/unit/test_batch_pipeline_intake.py` covers ordinary
admission and restore-origin unit/canonical/partial-parent fences across ledger
states; `tests/unit/test_batch_pipeline_live.py` covers ordinary speech revival
and the replacement repro; `tests/unit/test_restore_recording_obligation.py`
covers failed restore metadata through real admission and strict transactional
assignment. Both repros remain unmarked by xfail. No env, wire, payload,
workflow, or production data changes. `utils/batch_pipeline/live.py` is untouched.
`tests/unit/test_record_partial.py` retains its unchanged staging-race regression
for discarded partial-parent continuations.
The archive-filter fixture preloads the real stage helper before closing its
`utils` import path; its archive assertions are unchanged.
