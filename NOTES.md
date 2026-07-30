# M-skeleton assumptions

- The lifecycle kernel uses `provisional`, `canonical`, `deferred`, and `rejected` only as bookkeeping states. `defer_review` is a consolidation disposition, while liveness/retraction remains outside this offline experiment.
- `scope_ref` is nullable to represent explicit scope abstention; its non-null value is intentionally opaque and strategy-owned.
- Fixture timestamps and monotonic sequence values are synthetic deterministic test data, not production defaults.
- T7 is an offline placement experiment: it validates an already-supplied batch shape but does not implement the B3 lease, transaction, outbox, or concurrency contract. `defer_review` is bounded by the supplied retry budget and requires a re-resolution trigger.
