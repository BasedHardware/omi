# Class 11 attention expiry

Unresolved `recovery_structure_unavailable` attention items expire lazily after
seven days when still non-retryable. Expiry compares the observed state and
update time in a transaction and reads the common retry claim before writing,
so a stale poll cannot deactivate concurrent retry work. Transient failure
reasons stay visible; naive timestamps use UTC and ISO timestamps are normalized.
Filtered rows no longer consume the pending-work attention window.

The default-on `PROCESSING_ATTENTION_NON_RETRYABLE_EXPIRY_ENABLED` ops switch
is wired into the runtime base and matching GKE chart env. Set it to `false`
and recompose the manifest to stop new expiry; expired documents remain inactive.

Contracts: [failure terminal recovery](../../listen_pusher_pipeline.mdx#failure-terminal-summary-recovery)
and [pending work](../../pending-work.md). Regression evidence is in
`backend/tests/unit/test_pending_work.py`; PR #25028 records verification and
merge-order requirements. No deployed-behavior claim is made by these tests.
