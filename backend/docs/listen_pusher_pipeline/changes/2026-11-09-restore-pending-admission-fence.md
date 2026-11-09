# Restore metadata fences recording admission

Recording restore registers its durable obligation before committing visibility
metadata. If that metadata transaction fails, the conversation stays discarded
and the obligation stays retryable. Admission now reads the conversation inside
its transaction on every record path, including full archives and replay, and
refuses a discarded target with the existing retryable refusal.

Record replacement preserves automatic discards and their relevance verdicts
even when the final pass adds speech. Only the explicit restore metadata
transaction (`restore_conversation_from_discarded`) clears the discard; a
registered obligation alone does not authorize making the conversation visible.

This ships on with no new flag. Revert the PR to roll back. Regression coverage:
`tests/unit/test_restore_recording_obligation.py` exercises metadata failure
through real recording admission, and `tests/unit/test_batch_pipeline_live.py`
checks that replacement preserves a discard until restore commits. No env,
wire, or payload contract changes.
