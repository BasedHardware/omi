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
serving composition roots (`main.py` and `pusher/main.py`) inject the cached
resolver into the pure `config.rollout_cohorts` boundary. Existing Dream and
batch-recovery operator CLIs bind the same resolver at their entrypoints. Configuration imports
no database or serving utilities. `database.rollout_cohorts` owns only lazy
Firestore transport; `utils.rollout_cohorts` owns caching and the bounded executor. Async misses enqueue a bounded, isolated
read and deny until it completes; listen and pusher await their initial read for
up to 1.25 seconds before admission. The HTTP auth
worker preloads the same cache. OIDC sync tasks, the shared sync coordinator,
Dream pass admission and every model turn, pusher finalization shadow admission,
mobile batch renewal and live-demand handovers await it before
making rollout decisions. Warm awaits return immediately without a read; cold
and expired async decisions wait for the bounded read instead of silently
choosing the legacy path. No Firestore I/O runs on the event loop.
Expired grants are never served while refreshing. Live audio archive phase
admission is snapshotted at first use after listen warmup and remains stable
for that admitted connection; cohort changes affect it on reconnect. This
avoids packet gaps during a cache refresh. Other cohort checks retain the
60-second cache contract. Saturation and read errors
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

Cloud Run manifests omit private UID entries so a merge keeps the current live
values. **Helm listen/pusher values retain every legacy allowlist in this PR**:
Helm replaces its env list, so deleting them here would change live membership.
Their removal requires a separate PR after seed and verification. First-summary
empty or absent keys deny nonmembers, preserving main #22113. Sync-lineage
empty **and absent** keys retain their previous allow-all fallback if the
Firestore field is missing; explicit booleans still win. Dev therefore keeps
lineage enabled for everyone without enumerating users. Prod listen retains its
nonempty legacy lineage list. Percentages and parent gates stay unchanged.

The retained keys include `STT_LIVE_DEMAND_UID_ALLOWLIST` (prod listen),
`MOBILE_STANDARD_BATCH_UIDS` (prod listen), `DREAM_AGENT_UID_ALLOWLIST` (prod
listen/pusher), `SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST` (prod listen),
`SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST` (prod speaker detail),
`AUDIO_ARCHIVE_UID_ALLOWLIST` (dev listen/pusher coalesce), and
`TRANSCRIPTION_SHADOW_UID_ALLOWLIST` (dev pusher release probe). Other legacy
entries, including final-pass and recovery, are retained too. The prod
`OMI_MESSAGING_CHANNEL_POLICY` is omitted entirely: Cloud Run must retain the
live policy, including its iMessage cohort, instead of receiving an empty list.

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

## Live seed and verification (lead only, before deployment)

Use the current **live** sources, never a UID copied from Git or a historical
receipt. These commands read the four serving Cloud Run revisions in the
selected compute project and the installed listen/pusher Helm values via an
explicit Kubernetes context. Both environments use the `based-hardware`
customer Firestore data plane and `prod-operator`. The tool captures CLI errors
and prints cohort counts only; neither source payloads nor UIDs are printed or
saved. A failed CLI read, secret-backed/duplicate binding, split Cloud Run traffic,
source disagreement, over-limit cohort, or source change during seed blocks the
operation. It does not silently skip a missing service/release.

Set `COHORT_ENV` to `dev` or `prod` and `COHORT_KUBE_CONTEXT` to the verified
context for that environment's live GKE cluster. Freeze membership configuration
and operator mutations through seed, verify and deployment. Do not run a chart
upgrade or edit allowlists concurrently.

```bash
source ~/.local/bin/gcp-agent-env.sh prod-operator && \
backend/.venv/bin/python backend/scripts/rollout_cohort.py \
  --project based-hardware --environment "$COHORT_ENV" \
  --kube-context "$COHORT_KUBE_CONTEXT" --seed-live --dry-run
```

The default seed dry run reads live env/Helm, prints counts for every cohort,
and creates no Firestore client or writes. This differs from the single-member
file dry run above, which performs no reads at all. If live hosts declare
different lists, the command prints counts and `MISMATCH` and fails before any
Firestore client is created. **Do not union those lists**: a shared environment
cohort cannot represent host-specific membership without widening access.
Resolve that as a separate, explicitly reviewed policy/scoping decision while
keeping all legacy bindings; do not deploy this cutover until verification is
clean. Empty cohorts and independent percentage ramps remain distinct.

Only after the lead has reviewed the dry run:

```bash
source ~/.local/bin/gcp-agent-env.sh prod-operator && \
backend/.venv/bin/python backend/scripts/rollout_cohort.py \
  --project based-hardware --environment "$COHORT_ENV" \
  --kube-context "$COHORT_KUBE_CONTEXT" --seed-live --apply
```

Seed checks for unexpected existing Firestore grants and refuses to revoke or
union them. It atomically merge-writes the exact finite live memberships,
preserving unrelated fields/environments. Existing false fields for intended
members become true, matching live admission. It re-reads live sources before
committing and is idempotent. Universal legacy cohorts (dev lineage, public
Telegram) are not enumerated or converted into a finite UID list; they are
reported as `legacy_all=1` and retain their existing runtime contract. A false
lineage field blocks that universal migration. Do not remove this fallback in
the later env-removal PR without an explicit representation of allow-all.

Read-only verification compares exact sets, not just counts, including unexpected
Firestore members, and exits nonzero on any mismatch:

```bash
source ~/.local/bin/gcp-agent-env.sh prod-operator && \
backend/.venv/bin/python backend/scripts/rollout_cohort.py \
  --project based-hardware --environment "$COHORT_ENV" \
  --kube-context "$COHORT_KUBE_CONTEXT" --verify-live
```

## Deployment order and rollback

1. **Seed first:** the lead runs live dry run, seed apply, then read-only verify
   separately for dev and prod. Every cohort must match. The PR author does not
   seed production. Keep the current live memberships, including the dev audio
   pilot and pusher probe; do not infer one cohort from another.
2. **Switch reads second:** after approval/merge and release qualification,
   deploy the cohort-aware image and matching manifest through the owning GitHub
   workflows. Cloud Run preserves omitted legacy env; Helm retains every legacy
   value. Prod iMessage keeps the live policy. No config-only removal or kept-old-
   image cutover is permitted. Running artifact identity and a new admission/
   outcome metric or log are required; tests and CI do not prove live acceptance.
3. Re-run verify against the live sources, and check intended members,
   nonmembers, independent percentage cohorts and lineage allow-all. Confirm
   `OMI_BACKEND_RELEASE_SHA` or image-source digest on every affected service.
   Test read failure and explicit revocation after the 60-second TTL with a
   separately authorized canary.
4. **Remove env last, in a separate PR:** only after both environments are seeded
   and verified, with universal and differing-host policies explicitly resolved.
   This PR must not delete listen/pusher legacy values. Keep a private rollback
   snapshot until cutover is accepted.
5. Roll back the cohort-aware image and its matching config/chart to the prior
   release. The retained legacy values preserve the old membership. To stop new
   admission, use the existing feature kill switch. `--remove` writes a false
   tombstone and takes effect after up to 60 seconds plus a bounded in-flight
   read; it is an intentional membership change, never part of seeding. Already-
   admitted obligations keep their existing draining rules.

### Dream outage handling

Dream distinguishes unknown membership from a negative grant. Its independent
`all`/paid eligibility policy survives membership read failures, with no invented
allowlist or on-demand grant. An allowlist-only pass waits without deleting its
due row on a read failure. Empty discovery emits
`event=dream_cohort_health outcome=empty`; an unavailable read emits
`outcome=unavailable`, plus `omi_fallback_total` with
`from_mode=dream_cohort,to_mode=declared_eligibility`. These are operational
failures to investigate, never proof that the whole fleet was intentionally
excluded. Ordinary canonical memory intake does not depend on this cohort.
