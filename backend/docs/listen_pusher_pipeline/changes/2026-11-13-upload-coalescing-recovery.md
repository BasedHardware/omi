SCA-1800's default-off upload coalescing now checkpoints a fair scan cursor in
the global quota row. Privacy-denied holds keep their custody and fences while
later owners can drain, including after restart and with the producer OFF.

Merged admission freezes original receipt membership in its content ledger.
The normal all-sibling projection completion transaction completes each original
receipt before the merged target can expire. Client polling is not required to
materialize that proof; retries preserve the first terminal retention deadline.

The 600-second stale guard is unchanged. Read, quality, deployed-runtime and
latency qualification remain outstanding; the new fixed scan and per-member
fanout costs belong in the billed-read numerator. No activation or savings is
claimed. Compatible completion writers, readers and drainers must precede
producer activation. See `backend/docs/runbooks/batch-upload-coalescing.md`
and PR #25159 for the protocol, evidence and R11 release gates.
