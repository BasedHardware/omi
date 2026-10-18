# Private rollout cohorts

Membership is server-owned user data in `rollout_cohorts/{uid}`:

```json
{"cohorts":{"prod":{"batch-pipeline":true,"first-summary":true},"dev":{}}}
```

This follows `testers/{uid}` / `is_tester_db`, using the existing customer-data
Firestore client and credentials on both Cloud Run and GKE listen/pusher. No
Secret Manager resource, new credential, Helm env override, or collection setup
is required. Client Firestore access stays denied by the existing default-deny
rules; no client API accepts cohort mutations. Account deletion also erases this
top-level document and retries if that erase fails.

Dev and prod share the `based-hardware` customer data plane. Membership maps
are therefore namespaced by the existing `OMI_ENV_STAGE`, never by the compute
project. Dev-only members cannot enter production cohorts. Local/offline runs
use separate namespaces. Background discovery queries and their cache keys are
scoped to the same environment. No new env binding is needed.

One document per user gives one point read for **all** their cohorts, never a
collection scan on a serving request. A shared document per cohort would reduce
reads for very many cold users but would fetch every member's UID, concentrate
writes on a hot document, and grow toward Firestore's document-size limit.
User documents avoid those constraints and keep each operator mutation to one
merge write. Only Dream allowlist discovery and batch quarantine recovery query
members by an indexed boolean field; those background scans cache results for
60 seconds and fail closed at 500 members rather than silently truncate.

## Cache and migration semantics

`in_rollout_cohort(uid, name)` shares a bounded 4,096-user per-process LRU cache
across flags. Positive, missing-document, negative, malformed-document and error
results have a 60-second TTL. Concurrent misses for one UID share one read.
Firestore reads have a one-second RPC timeout and SDK retries disabled. The
serving executor injects the background submitter into the cache; the database
module never imports serving utilities. Async misses enqueue a bounded, isolated
read and deny until it completes; listen and pusher await their initial read for
up to 1.25 seconds before admission. The HTTP auth
worker preloads the same cache. No Firestore I/O runs on the event loop.
Expired grants are never served while refreshing. Saturation and read errors
deny membership; neither an SDK error nor the UID/document path is logged.

A warm check costs **0 document reads per request**, regardless of flag count.
An active resident UID costs approximately one document read per process per
60 seconds. At `r` requests/second for that UID in that process, the amortized
cost is about `1/(60*r)` reads/request (0.000167 at 100 requests/second).
Cold starts, low-frequency users and LRU eviction incur cold reads; this is not
zero cost for every request. Multiply by active processes; there is no shared
cross-process cache. Background member discovery has separate query charges.
[Firestore bills document reads and query results](https://firebase.google.com/docs/firestore/pricing).

A Firestore boolean in the selected environment is authoritative for its named
cohort. `false` revokes even a retained legacy env member. An absent field falls back to the existing
nonempty `*_UID_ALLOWLIST` / `MOBILE_STANDARD_BATCH_UIDS` env list, or to the
legacy messaging policy cohort. An unreadable/malformed document never falls
back. Keep removal tombstones during migration; deleting one could restore an
old env grant. Independent percentage rollouts, existing global policy (`*`),
kill switches, eligibility checks and already-admitted durable work retain their
contracts. Removing membership does not override a separate percentage rollout.

Public manifests and listen/pusher chart env lists omit all UID allowlist keys.
First-summary and sync-lineage now distinguish **absent** (Firestore membership)
from the explicitly configured legacy empty value (the previous enable-all
contract). Thus Helm env replacement cannot widen either cohort. Production
percentage/ramp/feature switches are unchanged, including live admission off.

## Operator commands

Use a private file containing only the target UID (`$DAVID_UID_FILE` below).
Do not put a UID in argv, shell history, public config, PR text or logs. The script
prints only the operation/cohort names, never the UID or SDK error text.
Dry run is the default and makes no client, read or write:

```bash
backend/.venv/bin/python backend/scripts/rollout_cohort.py \
  --project based-hardware --environment prod --uid-file "$DAVID_UID_FILE" \
  --cohort batch-pipeline --add --dry-run
```

To put David in the batch-pipeline cohort (one document merge write):

```bash
source ~/.local/bin/gcp-agent-env.sh prod-operator && \
backend/.venv/bin/python backend/scripts/rollout_cohort.py \
  --project based-hardware --environment prod --uid-file "$DAVID_UID_FILE" \
  --cohort batch-pipeline --add --apply
```

To revoke that membership, run the same command with `--remove` instead of
`--add`. It writes `false`, preserving unrelated cohort fields. Repeatable
`--cohort` arguments let an operator seed several cohorts in the **same write**.
Both existing dev and prod runtimes use `--project based-hardware` and require
`prod-operator`; select `--environment dev` for dev-only membership. The project
option names the **data plane**, not the compute environment. Use
`--project based-hardware-dev` with `dev-operator` only for an isolated runtime
whose data plane is actually that project. No human tier is needed.
Use `--help` for the complete reviewed name list. Membership alone does not enable
the live-admission switch or any other feature's parent gate.

## Deployment order and rollback

1. Before deploying, the lead seeds the intended memberships privately with the
   script. Preserve each existing cohort independently; do not assume batch
   admission also grants recovery, first-summary, Dream or messaging access.
   For a no-gap migration, seed the current owners of every removed nonempty
   list in its original environment; never union dev and prod memberships, including the dev audio-archive pilot if it is still wanted.
   Ledger-drain's old dev pilot is intentionally closed by removal of its
   private env binding; it is not one of the serving cohorts managed here.
2. Deploy the cohort-aware image and manifest from the **same commit** through
   the owning GitHub workflows. Do not apply this branch's chart/env removal to
   an old image. Cloud Run's env merge can retain old literal values: those remain
   a migration fallback, overridden by any explicit Firestore boolean. GKE Helm
   replaces the env list, so the new image must resolve Firestore in that same
   release. Neither platform requires new env entries to see membership edits.
3. Verify the running `OMI_BACKEND_RELEASE_SHA`/image-source digest on all
   affected services, then observe a new admission/outcome log or metric from
   a lead-owned canary. Check an intended member and a nonmember, failure denial,
   and revocation after 60 seconds. Check listen specifically: reconnect after
   cache expiry and confirm batch-owned admission without `kubectl set env`.
   Watch existing percentage cohorts separately. Unit tests/CI are not live
   acceptance; no production user-data reads or canary are performed by this PR.
4. To stop new batch admission, use its existing feature kill switch through a
   reviewed config deploy. To remove one cohort member, use `--remove` and wait
   up to 60 seconds (plus an in-flight bounded read). To roll back code, restore
   the previous image **and matching previous manifest/chart** atomically per
   service. Rolling back only the image while leaving allowlists absent can
   trigger legacy enable-all semantics. Do not restore literal UIDs to Git;
   retain a private rollback artifact/operator binding until migration is done.
   Already-admitted recovery obligations keep their existing draining rules.
