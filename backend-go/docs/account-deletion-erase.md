# Go queue account deletion

The Python deletion executor owns billing, grace, legal holds and the account wipe. Once
a wipe is due and billing cancellation succeeds, it records the claimed generation on the
authoritative Firestore deletion marker. Workerd verifies the caller and the marker, runs
Lane B's committed queue-only purge, and returns the generation and claim. The executor
records a receipt and then a wipe-start timestamp under the same generation and lease.

An unavailable workerd leaves the wipe pending unless the recovery connection can commit
the same Postgres operation. A mismatched or unauthorized request fails closed. Firestore
receivers continue to fence late writes after a queue database session disappears.

## Enablement and rollback

1. Ship with `GO_QUEUE_ERASE_REQUIRED=false` (the default in every environment). Existing
   deletion paths still run without contacting Go. Configure the private HTTPS listener
   and give it normal queue access. Set `ERASE_FIRESTORE_PROJECT` and
   `ERASE_FIRESTORE_DATABASE` to the authoritative project and database resolved by the
   Python deletion executor. Use `(default)` explicitly for the default database. Omit
   `ERASE_PORT` when the listener is disabled. An explicitly empty port is invalid.
2. Lane B owns the queue migration and the separately applied recovery access migration.
   David must approve the new recovery role before any access change. After approval,
   provision the environment-specific login or IAM binding for the EXECUTE-only role,
   supply `GO_QUEUE_ERASE_RECOVERY_DATABASE_URL` via an approved secret binding and set
   `GO_QUEUE_ERASE_RECOVERY_SCHEMA` to the schema used by workerd. An absent recovery URL
   disables recovery. Both Lane B dependencies must reach main before merging this
   barrier. Verify both paths target the same queue using a synthetic tenant.
3. Wire aggregate readback and paging in the environment as described below. Exercise both
   erase paths and a workerd outage with synthetic tenants. Confirm the armed receipt and
   wipe-start timestamp ordering. The queue and Firestore fences must both be active.
4. Let wipes that began removing data under the old behavior finish before enabling the
   barrier. Preserve and audit existing wipe-start evidence for any legacy retry.
   In the first live family's release, set `GO_QUEUE_ERASE_REQUIRED=true` for the Python
   Cloud Tasks deletion executor and supply `GO_QUEUE_ERASE_URL` and `GO_QUEUE_ERASE_AUDIENCE`
   before admitting any live tenant traffic. The URL is a private TLS endpoint at
   `/internal/v1/tenant-erase` and the audience is that service's configured OIDC audience.
5. Roll back the switch only as part of disabling all live Go tenant traffic. Stop new
   work, drain or erase remaining tenant queue rows, and finish armed deletions before
   turning it off. Already armed generations continue to require a receipt.

## Readback and escalation

From the backend runtime with the approved read-only marker identity, schedule
`python -m scripts.read_go_queue_erase_sli` every five minutes. Its JSON contains the
count due for readback, the count with a durable acknowledgement within 15 minutes of
arming and before the first data wipe step, and the overdue pending count. The cohort is
the trailing seven days, excluding the 15-minute grace for measurement. Empty cohorts
publish a null ratio. Pending and failed generations count as misses once mature.

Page the deletion owner for positive `overdue_pending`, `met < eligible`, a missing
scheduled readback, or `go_queue_erase_page` on a rejected attempt. The page contains
the reason. Use the restricted deletion failure logs and authoritative marker to locate
the affected generation. For a rejection,
correct the listener TLS or workload identity, database permissions, or marker authority
reported by the failing component, then replay the same current generation through the
deletion reconciler. A rejection on a retry cannot settle the outcome of an earlier
attempt. Keep its legal-hold gate fenced until the same operation has a committed receipt. Acceptance is a 100% ratio with a visible numerator and denominator.
A shared Postgres outage keeps the wipe pending. Restore or fail over the queue store,
preserve or reapply erasure tombstones before restoring worker traffic, and replay the
same barrier. Neither time nor a workerd restart is an erase receipt.
