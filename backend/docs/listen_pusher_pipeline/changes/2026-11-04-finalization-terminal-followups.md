# Finalization terminal follow-ups

Delivery-independent exhausted-requeue terminalization now shares the worker's
failure-code folding and post-commit terminal effects: usable transcripts keep
`summary_retryable`, terminal metrics run, Typesense converges, and quiet checks
retire only after the terminal transaction commits. No flag or rollout change.

Terminal BYOK jobs log at WARNING, and typed `byok_invalid_key` account-state
responses follow the admission guard's warning path without a provider traceback.
See [the BYOK logging contract](../../runbooks/byok-provider-failures.md).

Regression evidence: `tests/unit/test_finalization_replay_exhaustion.py`,
`tests/unit/test_listen_finalization_cloud_tasks.py`, and
`tests/unit/test_conversation_lifecycle_contract.py`. Follow-up to #23877,
Cloud Run review P2s 2–5 (bus ddb9b0). Rollout requires a backend Cloud Run train.
