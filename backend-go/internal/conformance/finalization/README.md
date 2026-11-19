# finalization

This package uses the queue's public methods and owns all conversation policy. Admission commits the tuple before writing the document binding. A worker automatically repairs an interrupted admission. The tuple stays stable for replays, and a valid explicit reprocess creates a distinct revision. A discarded, deleted or tombstoned document cannot be rebound.

The document holds notes and extraction checkpoints and the fanout claim. SQL holds identifiers, attempts and sink progress only. The exact joined transcript and deployment implementation version determine the input hashes. Notes have a recoverable checkpoint before the public structured write. Enhanced memory content is sealed both in the extraction checkpoint and at the memory sink. Derived writes present the conversation's binding and revision. Integrations present the shared fanout key and have independent durable receipts.

The finalization handler reconciles a terminal intent before the queue parks it. A completed fanout takes precedence over an exhausted lease. A first platform transient exhaustion schedules one budget requeue. A final failure keeps the transcript visible and preserves already available structured notes. BYOK work uses the request key only in the live worker invocation or its bounded replica-local scheduling timer.

| Rules | Regression tests |
| --- | --- |
| F1–F3 admission and revision | Public `test_repeat_admission`, `test_invalid_trigger`, `test_missing_conversation` and system `test_recover_admission_and_checkpoints`, `test_budget_exhaustion_and_revision_rules` |
| F4 live key and abandonment | `test_own_key_abandonment_and_resume`, `test_own_key_future_resume` |
| Steps 1–5 and transcript protection | Public `test_happy_path`, `test_discard`, `test_read_production_enhanced_compressed` and system `test_encoded_paths_and_bad_ciphertext` |
| Steps 6–10 and F8 fencing | `test_fanout_commit_wins_at_final_attempt`, `test_webhook_delivery_progress_and_final_drop`, `test_rate_limited_webhook_and_vector_are_best_effort`, `test_erase_across_replicas_and_delete_fence` |
| F5 and F6 pending, transient, deterministic | Public `test_one_retry`, system `test_pending_yields_and_account_marker`, and wire fault classification tests |
| F7 and F9 dead letter and one budget requeue | `test_budget_exhaustion_and_revision_rules`, `test_encoded_paths_and_bad_ciphertext` |

## Queue API it uses

`Work` returns a `queue.Outcome`; `Exhausted` gets a `queue.Reconcile` and returns a
`queue.Resolution`. The account check runs inside a guard at the start of `Work` and holds the
whole tenant while its owner is being deleted. The batch cases use `internal/batchunit` with the
adapters in `internal/conformance/stubapi` and the kit's payload tables in
`internal/conformance/kitstore`.
