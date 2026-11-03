# Sync-on batch conversations get a whole-conversation speaker pass

Enrichment runs the shared final pass after speaker resolution/evidence projection
and before summary construction. The [runbook](../../runbooks/batch-conversation-speakers.md#whole-conversation-final-pass-sync-on-slice)
defines flags, budgets, mapping proofs and rollback; the
[batch speaker contract](../../listen_pusher_pipeline.mdx) remains the authority for
projection ownership and manual receipt precedence.

The new default-on kill switch and default-100 percent sit inside existing batch
authority. A store-specific PCM assembler plus exact unit PCM proof connects
original unit words to stable segment IDs. Missing proofs abstain; stored segment
start/end and text matching do not provide alignment. Shared community-1 naming
retains thresholds and owner arbitration; manual receipts take precedence.

This slice serves sync-on only and preserves existing per-unit diarization. It
writes no enrollment or audio artifacts and extends no retention deadlines. The
lead ramps 10/50/100 using fallback rate, owner-parity delta, p95 enrichment latency
and diarizer-batch queue depth. Estimate 0.03–0.042 GPU-hours per admitted audio-hour.
Hermetic tests exercise admission, rollback, independent stores, unplaceable units,
manual authority, length limits, atomic budgets, privacy revocation and GPU errors.
