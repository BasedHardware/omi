# Go queue account deletion

The Python deletion executor owns billing, grace, legal holds and the account wipe. Once
a wipe is due and billing cancellation succeeds, it records the claimed generation on the
authoritative Firestore deletion marker. Workerd verifies the caller and the marker, runs
Lane B's committed queue-only purge, and returns the generation and claim. The executor
records a receipt and then a wipe-start timestamp under the same generation and lease.

An unavailable workerd leaves the wipe pending unless the recovery connection can commit
the same Postgres operation. A connection or handshake timeout is an availability failure. TLS verification, identity,
and claim rejections fail closed. Firestore
receivers continue to fence late writes after a queue database session disappears.

## Enablement and rollback

1. Ship with the barrier off. The deployment manifest renders one
   `go_queue_erase_required` boolean into `GO_QUEUE_ERASE_REQUIRED` for all backend
   runtimes in that environment. An unset or false value preserves legacy deletion,
   including the same reads and writes. Configure the private HTTPS listener
   and give it normal queue access. Set `ERASE_FIRESTORE_PROJECT` and
   `ERASE_FIRESTORE_DATABASE` to the authoritative project and database resolved by the
   Python deletion executor. Use `(default)` explicitly for the default database. Omit
   `ERASE_PORT` when the listener is disabled. An explicitly empty port is invalid.
   By design, an invalid TLS configuration or a failure to bind the enabled erase
   listener shuts down the entire workerd process. The deployment cannot serve with
   a broken erase listener.
2. Lane B owns the queue migration and the separately applied recovery access migration.
   David must approve the new recovery role before any access change. After approval,
   provision the environment-specific login or IAM binding for the EXECUTE-only role,
   supply `GO_QUEUE_ERASE_RECOVERY_DATABASE_URL` via an approved secret binding and set
   `GO_QUEUE_ERASE_RECOVERY_SCHEMA` to the schema used by workerd. Set a single TLS
   verification hostname (`host`) and its numeric `hostaddr` in the DSN so recovery
   can honor its deadline without DNS. Pin `GO_QUEUE_ERASE_RECOVERY_QUEUE_ID` using
   the read-only check below. Recovery stays disabled until both the DSN and a
   verified pin are configured. Both Lane B dependencies must reach main before
   merging this barrier.
3. Wire aggregate readback and paging in the environment as described below. Exercise both
   erase paths and a workerd outage with synthetic tenants. Confirm the armed receipt and
   wipe-start timestamp ordering. The queue and Firestore fences must both be active.
4. Let wipes that began removing data under the old behavior finish before enabling the
   barrier. Preserve and audit existing wipe-start evidence for any legacy retry.
   In the first live family's release, configure Cloud Tasks dispatch and supply
   `GO_QUEUE_ERASE_URL` and `GO_QUEUE_ERASE_AUDIENCE` to the executor. The erase URL
   is a private TLS endpoint at `/internal/v1/tenant-erase`; the audience is that
   service's configured OIDC audience. Set `overlay.go_queue_erase_required: true`
   in the target environment's source overlay under `backend/deploy/runtime_env/`
   and regenerate the deployment manifest. Leave service-level overrides unset.

   Roll all revisions and pods that serve admission, restore, grace reconciliation,
   or Cloud Tasks execution from the same rendered configuration. Verify the
   effective value on each serving revision and pod. Drain older revisions and
   in-flight work that saw the off value before admitting live Go tenant traffic.
   Verify with synthetic accounts that admission retains credentials and a worker
   outage leaves them untouched. With the barrier enabled, the executor deletes
   credentials after the committed erase receipt.
5. Roll back the switch only as part of disabling all live Go tenant traffic. Stop new
   work, drain or erase remaining tenant queue rows, and finish armed deletions before
   turning it off. Set `overlay.go_queue_erase_required: false` explicitly and roll the
   same runtimes. Omission can preserve a previously deployed environment value.
   Already armed generations continue to require a receipt.

## Verify the recovery queue binding

Run this read-only query from the backend checkout using the intended workerd writer's
connection and queue schema. Source the DSN from workerd's approved configuration into
`WORKER_QUEUE_DSN` for the check. Use a TCP connection to that writer.

```bash
python - "$WORKER_QUEUE_SCHEMA" <<'PY'
import os
import sys

import psycopg

from services.users.go_queue_erase import RECOVERY_QUEUE_ID_SQL

with psycopg.connect(os.environ['WORKER_QUEUE_DSN']) as conn:
    proof = conn.execute(RECOVERY_QUEUE_ID_SQL, (sys.argv[1],)).fetchone()
    if proof is None:
        raise SystemExit('No fingerprint for this writer and queue schema')
    print(proof[0])
PY
```

Use the result as the recovery pin and exercise the workerd and recovery routes with a
synthetic tenant. The recovery call compares that pin with the connected cluster,
database, writer address and queue tables in the same transaction as the erase. A
mismatch fails closed and records no receipt. A successful recovery includes the pin in
its Firestore receipt. Re-verify after a writer failover, address change, or queue
recreation before updating the pin.

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
