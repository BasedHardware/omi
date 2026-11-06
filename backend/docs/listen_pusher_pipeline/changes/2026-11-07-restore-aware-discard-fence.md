# Restore-aware discard fence for batch recording obligations

Finalization skips `register_recording` when processing persists a relevance
discard, avoiding registration retry churn for intentionally discarded live
captures. It combines the processed discard result with the original recording
and archive metadata, so a revival still registers its required `record_pending`
audio obligation before fanout.

The [durable fanout ownership fence](../../listen_pusher_pipeline.mdx) checks
`expected_discarded` inside the claim transaction. If a concurrent user restore
revives the current completed generation, the claim returns `lease_conflict`
without admitting fanout or terminalizing the job. Retry reloads the restored row
and registers its obligation. Missing, still-discarded, and superseded generations
retain the terminal stale outcome and exactly-once projection bookkeeping.

This fix is on without a new flag. It preserves the existing recording-owner and
proven-empty-archive rules. Unit regressions cover processing discard/revival,
registration refusal, silent backfill, and terminal fencing. The listen lifecycle
Firestore emulator harness holds a real restore transaction ahead of a concurrent
fanout claim, then verifies refusal and durable recording registration before a
successful retry. These are local lifecycle guarantees, not deployment evidence.

The hermetic listen-stack supervisor retains child handles until the leader is
reaped and its original process group is proved absent. Cleanup checks session
and UID ownership before each group signal, attempts every registered child,
and preserves a primary scenario exception alongside secondary cleanup errors.
Sanitized cleanup JSONL records launch identity, membership and poll/wait stages.
Signal denials remain failures; the earlier Darwin EPERM cause is unproven and
no denial-as-exit recovery is enabled. A first Darwin regression run exposed
`getsid` returning ESRCH for an enumerated unreaped zombie, and a separate bounded
`ps` timeout whose cause is unknown. Cleanup now polls/reaps its direct child
before metadata inspection and proves group absence with a kernel probe; unknown
zombie SID data never authorizes a signal. The finite zombie fixture captures
its live session before exit. A subsequent run passed real TERM/reap/idempotence
and zombie/reap, but the kernel-probe fixture encountered SID ESRCH after a
non-Z snapshot. Such rows now retain their observed state and an explicitly
unknown SID; only actual child reap plus independent kernel group-absence proof
can finish cleanup. Unknown observations never authorize signaling. The updated
cleanup regressions subsequently passed in the parent run (29/29), but the full
stack failed at pusher restart: after TERM timed out, the sole direct child's
KILL-stage census had SID ESRCH and state `?Es` while both polls still returned
`None`. Final close later reaped that same child with TERM status and proved
kernel group absence. This is a distinct non-waitable exit observation, not an
explanation of the historical EPERM.

For only that sole direct-child identity with matching PID/PGID/UID/PPID and an
unknown SID from ESRCH, cleanup now spends the existing five-second KILL wait
allowance on reap alone, without sending KILL. State and lookup failure prove
neither exit nor ownership. Actual reap and independent kernel group absence
remain mandatory; timeout, foreign/unknown surviving membership and denials
retain failure and the child handle. TERM, KILL and census bounds are unchanged.
Deterministic deferred-waitability regressions and full-stack acceptance remain
pending parent validation; no new behavioral pass is claimed.
