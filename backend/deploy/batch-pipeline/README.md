# Batch privacy retention

`retention.json` declares completion-only `expires_at` policies for jobs, result
logs, artifact references, intake mappings and projection receipts in both stage namespaces.
`scripts/batch_pipeline_ttl.py --project PROJECT` prints the exact plan offline.
The lead's authorized operator uses the same command with `--apply` and records
the returned ACTIVE states before any cohort rollout. This uses Firestore Admin
`updateMask=ttl_config`; it preserves existing single-field indexes. The central
index manifest intentionally rejects `ttl=true`, so TTL has a separate manifest.
No policy has been applied by this change.

`account-privacy-receipt-retention.json` separately declares a 90-day replay
window for the derived `account_operations` receipts. Preview it with
`scripts/batch_pipeline_ttl.py --project PROJECT --policy deploy/batch-pipeline/account-privacy-receipt-retention.json`.
The policy applies to `expires_at` on receipts. The owner row and durable epoch
head keep their existing lifetime.

Encrypted staged audio/result objects are erased 24 hours after successful
projection. `expire_completed_segment` arms cleanup only once the projection is
ready; the maintenance pump drains `cleanup_completed_artifacts`. Receipt TTL is
45 days, matching content-ledger replay retention. Object deletion happens before
its reference receives a TTL. Unprojected results, queued work and dead letters
have no expiry: retain accepted audio until successful completion or erasure.

Deletion persists intent first and erases all stage namespaces even with admission
off. A pre-upload artifact reference remains in the erasure outbox until its
2-minute in-flight IO window closes; the maintenance sweep erases it again and
removes the reference. Failed storage cleanup retains retry state. Hash-only
privacy generations and deletion authorities have no TTL, so a stale result cannot
reopen an account. The shared-live GPU reservation path is retired, so no
reservation outlives a purge.

Conversation erasure keeps only a content-free result ordering edge when a
predecessor has not projected yet. Its state is `erased`, with no result, URI or
source/target identity. `erased_predecessors` verifies these edges back to the
current cursor; projection expires them only after committing its cursor advance.
The erasure transaction advances a directly adjacent cursor itself. Account
erasure removes these receipts too. This keeps unrelated later work resumable
without permitting deleted content to project.
