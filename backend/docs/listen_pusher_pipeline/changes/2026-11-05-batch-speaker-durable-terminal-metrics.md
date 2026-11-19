# Recoverable speaker retry terminal counts

Dedicated speaker retry outcomes now increment a durable counter in the same
Firestore transaction that closes their reporting receipt. The obligation key
is the idempotency key. An ambiguous commit, duplicate wake or process loss
cannot lose or repeat the stored count, and recovery never repeats inference
just to report an outcome. The four-claim cap and whole-pass shared-unit refusal
are unchanged. Ineligible calls and deferrals remain outside terminal counts.

The existing maintenance sweep refreshes 16 fixed, content-free counter shards
into a process cache, even when no receipt is due. Prometheus scrapes do no IO.
Replicas mirror global totals in `omi_transcription_final_pass_retry_terminal_total`;
operators use `max` before increases, then combine with the initial-pass outcome
counter. The refresh timestamp distinguishes stale/missing observations from
zero outcomes. Failed metric reads do not block durable-row repair. No old
closed receipts are backfilled. GMP and the source-backed inventory include the
new counter and freshness gauge; the full histogram keep-list remains intact.

The [runbook](../../runbooks/batch-conversation-speakers.md#reading-final-pass-outcomes)
documents the query, partial per-segment application, preserved unplaced labels,
no recurring learning for partial coverage, refusal/deferral/exhaustion outcomes,
cleanup tombstone reasons and the read-only staged-unit harness. Rollout defaults
and deployment configuration are unchanged except the authorized GMP keep-list.
The parent owns rollout approval and the owner-data gate.
