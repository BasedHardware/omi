# Run held-input urgency on every maintenance tick

Review-desk #25010 at `18197cf7234` correctly identified that the ordinary
`next_at` return suppressed age urgency. Its next-day-delay explanation does not
match that revision: ordinary work set `next_at = now + 300`; only a completed
dead-held redrive pass waited for another UTC day. Urgency now precedes the sleep
check regardless of its stored deadline.

An urgency-only tick keeps the existing two 128-row indexed streams and
transaction-owned eligibility checks. It checkpoints only `input_after` through
the existing snapshot CAS, leaving ordinary/redrive state unchanged. The input
kill makes a sleeping tick read-only, with no urgency query or cursor write;
the enclosing held-sweep kill retains zero IO. No timer or index changes occur.

For the supplied dated 22,583-row cohort, the cadence bound includes an initial
wait plus 177 pages: `178 * T`. The serving sleep is 20 seconds by default and
at most 60 seconds: 59m20s or 2h58m, **plus actual maintenance/RPC runtime**.
Using a conservative 300-second completed-tick budget instead gives **14h50m**,
not the old 14h45m estimate. This requires successful ticks within that budget
and a stream no larger than the cited cohort; it is not an outage or refusal SLA.

Contract: [held staging input expiry](../../listen_pusher_pipeline.mdx#held-staging-input-expiry).
Timing assumptions and operator procedure: [runbook](../../runbooks/held-staging-inputs.md).
Regression coverage: `tests/unit/test_batch_input_retention_sweep.py` exercises a
row becoming due after a completed pass, both held legs, sleeping cursor progress,
competing checkpoint protection, skipped ordinary/dead pages and both kill switches.
Audio custody, expiry predicates, lifecycle and deployment bindings are unchanged.
