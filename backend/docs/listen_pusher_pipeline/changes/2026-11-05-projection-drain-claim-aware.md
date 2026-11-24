# Claim-aware batch projection drain admission

Duplicate owner requests now defer while another fleet walker holds the claim.
Only claim-busy re-requests back off; productive continuations keep FIFO progress.
Retry timers are capped and cleared on close, with overflow handed to the next serving pass.

The [kill-switch contract](../../listen_pusher_pipeline.mdx#batch-projection-drain-admission)
is default on. Prefetch and assignment fences are unchanged. Regression coverage:
`tests/unit/test_batch_pipeline_owner_drain.py` and `test_batch_pipeline_projection.py`;
GMP retains skipped-drain and claim-busy-backoff counters.
