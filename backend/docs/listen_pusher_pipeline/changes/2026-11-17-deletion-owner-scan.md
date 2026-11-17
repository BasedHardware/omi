# Sealed owner scans for conversation deletion

Backend-sync can share one resumable batch-history traversal across a bounded,
sealed group of the owner's fresh deletion obligations. Existing partial purges
keep their legacy cursor. Per-member tombstones, generations, leases, journals,
account gates, WAL erasure and storage settlement remain authoritative.

`CONVERSATION_BATCH_PURGE_COALESCING_ENABLED` defaults on; false/off/0/no hands
members back to legacy execution with their journals. Existing task payloads and
finite member leases preserve rollback reachability. Coalescing additionally
requires Release's expiring all-consumers-new readiness attestation at
`conversation_batch_purge_jobs/_owner_scan_v1_readiness`; absent/stale readiness keeps
legacy execution. Revoke readiness, switch off and drain groups before routing
old consumers, whose completion cannot fence re-arms.

The [runbook](../../runbooks/conversation-purge-coalescing.md) specifies the state
readers, design simplifications, rollback proof and separate canary train.
Validation is synthetic unit/Firestore-emulator evidence, not measured savings.
