# Shadow transaction contention labels

Shadow metadata transactions pass a static `batch_shadow_<operation>` name to
the existing Firestore contention retry logger. The closed operation set is
`finish`, `offer`, `reserve`, `ready`, `projection_input`, `take`, `paid`,
`handoff`, `start_recovery`, `recovery_transport_failed`, and `reap`.
Labels contain no account, worker, job, content, or provider identifiers.

The operation context resets on success and exceptions, preserving the enclosing
serving `batch_pull` / `batch_claim` context or the default
`batch_pipeline_store` label. Retry attempts, deadlines, backoff and transaction
semantics are unchanged. Disabling contention retry retains its existing behavior.

Compare exhausted/deadline-exhausted counts by image and operation over the same
window. These are event counts, not unit rates. Existing log association with a
same-pod shadow task failure is correlation, not proof of callback identity.
Contention remains alert-only; T1 custody, T2 measured lost speech, and T4 language
are the only automatic rollback signals. A deployment of these labels needs a
fresh observer that accepts this closed set; never edit a running observer.
