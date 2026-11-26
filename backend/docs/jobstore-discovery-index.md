# Firestore-authoritative recovery discovery hints

`BATCH_JOBSTORE_MODE=index` wraps the existing owner-sampled mirror.
Firestore remains authoritative for every transaction, lease, claim, paid
decision, privacy check and mutation. Default mode remains `firestore`.
The retained copy keeps its existing cohort/erasure contract; see
[production mirror prerequisites](jobstore-production-mirror.md).

Root approved the bounded `due_leased` **source contract** on 2026-11-17.
This supersedes the earlier assumption that recovery requires an exact global
prefix at every intermediate call. It grants no production activation,
artifact qualification, new latency budget or savings claim.

## Qualified route and controls

Generic production `IndexStore.due()` calls remain coverage-refused. The sole
exception is the `Scheduler.recover` gateway with a qualified source role:
`pump_recovery`, `serving_maintenance`, or `serving_reconcile` (including manual
reconcile). The caller role is supplied by the source callsite, never request
data. Unknown callers use canonical primary discovery. Retry/result-ready
production queries remain refused, and retry discovery runs independently.
No hint result is a drain, completion, backlog, priority or admission guard.

| Control | Behavior |
| --- | --- |
| `JOBSTORE_INDEX_QUERIES` | Exact allowlist; default `due_leased`. Empty/invalid uses primary. |
| `JOBSTORE_INDEX_READS` | `0`, `false`, `off`, `no` kills reads, including before returning SQL. |
| `JOBSTORE_SHADOW_WRITES` | Same off values kill hint reads as well as new copying. |
| `JOBSTORE_INDEX_RECOVERY_POLICY` | Default unset/primary. Exact `role_minute_v1:BPS`, ASCII integer 0..10000. Invalid/unset/stale policy uses primary. |

Existing namespace, deployment and complete target configuration are required.
The new gateway is default-closed in dev/staging too. Installing this source
does not preserve an earlier recovery-hint soak without an explicit exposure
policy; root/Release must bind that policy before accepting new staging evidence.
The configuration selects a conditional hint policy; it does not prove copy
coverage, installation, erasure readiness or runtime admission.

Exposure hashes the ASCII string
`omi:recovery-hints:role-minute:v1:{namespace}:{caller}:{floor(entry_unix_time/60)}`
with SHA256, interpreted as an unsigned integer modulo 10000, selecting buckets
strictly below BPS. The semantic unit is a logical **namespace/role/UTC-minute**,
shared across replicas and restarts. `100/10000=1%` describes hash buckets, not
jobs, invocations, owner copies, HTTP traffic, reads or cost. Count actual
selected/entry traffic; correlated replicas and uneven role traffic matter.
Unselected invocations execute full canonical primary discovery. Zero selects
none; 10000 selects every hash unit, subject to every other safety condition.
An entry whose UTC minute expires before SQL can return uses primary. Bind
runtime clock health and caller succession; invalid clocks cannot admit hints.

## Safety and candidate feedback

Every wrapper/process starts with the full canonical primary due query.
Factory reuse does not reset that guard. Successful primary-query **start**
sets a monotonic interval at most 60 seconds; completion wall time is separate
freshness evidence. Primary failure invalidates the interval. Per-query attempt
ordering prevents an older overlapping result from clearing newer backlog or
failure state. A primary-only gateway failure also invalidates cached hint
freshness across a later factory-mode change.

A full primary leased page keeps subsequent calls on per-call primary until a
short primary page. This preserves ordinary catch-up capacity. A primary prefix
blocker retains the baseline starvation behavior; a short page is not a global
drain/completion certificate. No global generation write, CDC protocol or
producer fence is introduced for this bounded-hint route.

SQL uses the existing warm pool only, read-only transaction, ordered inclusive
`lease_until <= now` predicate, key tie-break and limit clamped to 1..100.
Statement and synchronous driver-wait deadlines remain bounded (default 0.2s).
No connection dial, IAM refresh or surviving timeout worker enters discovery.
Kills, exposure policy and monotonic freshness are checked again after SQL.
Any failure, empty/full page, invalid shape/key or duplicate uses full primary.
At limit=1 no hint page can qualify.

Every candidate is re-read in the existing Firestore transaction and must still
be leased and due. State/lease ABA, heartbeat, deletion or a change to retry
cannot authorize a different transition. Existing privacy/owner checks remain
at the transaction boundary. After all hints, if no candidate produced an
authorized current transition, the caller runs full canonical primary discovery
and processes that page before retry discovery. This is a feedback fallback,
not a second full primary scan for every useful PG answer. A primary failure
raises; it cannot authorize a hint or an empty completion.
The context guard rejects a future caller that consumes PG hints without
candidate feedback or canonical fallback. It cannot silently complete an
unhandled all-ineligible answer; the actual Scheduler performs that fallback.

For an omitted candidate inside a successful canonical prefix, discovery delay
includes the mandatory primary cadence (at most 60s), measured caller gap,
sampled cutoff age and primary-query duration. There is **no unconditional
finite bound** during stalled callers, failed primary or blocked prefixes.
Five-second pump throttles and twenty-second supervisor ticks do not prove a
finite invocation gap; preceding maintenance and executors can stall. Existing
900s obligation/1800s job freeze, rollback trips and prior-hour SLO/custody
guards remain binding. Source approval grants no new user-visible budget.

## Count and cost denominators

`omi_jobstore_recovery_discovery_total{namespace,caller,event,source,reason}`
counts every `Scheduler.recover` entry, including migration failure, unknown
callers, Firestore mode, invalid allowlists and factory bypasses. Events are:

- `entry`: one recovery invocation; not one row, owner, replica or transaction.
- `selected`: a valid live policy selected the entry's logical hash unit.
- `eligible`: pre-SQL freshness, backlog and configuration gates allow a hint,
  before the exposure decision. This is not population completeness.
- `pg_attempt`, `primary`: actual leased discovery attempts, including failures.
- `candidate`, `useful_candidate`: primary candidate transactions attempted and
  authorized transitions committed, attributed to hint/primary discovery.
- `completed`, `error`: terminal caller outcome; all-ineligible PG feedback
  ends on primary. A PG attempt is not itself a successful hint result.

Caller-gap, cutoff-age and primary-query-duration histograms provide count/sum
and buckets. Gaps are monotonic between actual entries per process/role;
cutoff age is sampled when discovery starts after migration. No gap series on
the first entry proves an interval. Combine these with failures, active caller
binding and source identity; a fleet maximum can hide a stalled active caller.

The existing `omi_jobstore_index_primary_scan_success_timestamp_seconds`
records actual successful primary completion (including empty, killed,
unselected and feedback fallback scans). It now also covers primary-only
factory bypasses for leased recovery. PG, failures, parity and scrapes do not
advance it. Absence/future timestamps/stale scrapes are UNKNOWN. Namespace
labels are `batch_pipeline_dev`, `batch_pipeline_prod`, `other`; role/event/
source/reason sets are finite. No IDs, customer content or minutes are labels.
The legacy `omi_jobstore_index_reads_total` reason `hint_ineligible` also
includes gateway-refused primary scans; the caller counter distinguishes
`unknown_caller` and `excluded` from actual candidate-feedback fallback.
The same collectors export in default and GPU private registries in all modes,
even if optional shadow/driver imports fail.

Let N be caller entries, P actual leased primary queries, H PG attempts.
Fallback contributes to both H and P. N-P is only a nominal upper bound:
entries that fail before leased discovery also have no primary query and must
not count as removal. Use successful `completed{source="postgres"}` recovery
counts over N for completed useful PG-only work; retain error/none entries in
the invocation denominator. PG attempts alone do not establish read removal.
Candidate transactions, retries, migration, unchanged retry discovery, mirror
rereads, parity and index-entry work remain in the cost denominator. Optional
parity can enqueue after both PG and its feedback primary fallback; a dropped
comparison is UNKNOWN. These counters do not establish billed savings.

The preserved historical1190 actual-source 2000/100 burst witness shows bare 60s sweeps leave
400 leases at 900s; canonical per-call and primary-full catch-up clear by 95s
at 5s invocations. Its 147 nominal removed queries also add 147 missing-ID
transactions: no net savings claim follows. The fast unit case scales the same
20-page workload to 40/2. An ideal useful short-hint 5s window can remove 11 of
12 primary queries; empty/full/killed/catch-up windows remove zero. Actual
usefulness, conditional exposure and net cost must be measured at runtime.

## Runtime gates and inverse

Production eligibility is zero until root+Release accept the actual artifact,
qualified caller/producer roster, retained-copy and erasure obligations,
runtime/operator state, clock/gap/capacity, parity, SLO/custody and effect gates.
The first eligible leased slice remains ASAP/latest November 18, not a calendar
wait. Expand only after actual counts and the full predeclared new-state
lookback plus two fresh scrapes, retaining prior-hour guards. Retry/result-ready
need separate contracts; final PG authority/A7/G2 remains reserved, with no D
dependency. A source merge, shadow mode or sampled-prefix parity is not rollout.

Inverse: unset the recovery policy (or BPS0), `JOBSTORE_INDEX_READS=off`, or
Firestore mode. Verify canonical primary for the same active callers. Retain
copy target and synchronous erasers until retained-copy obligations end.
No copy/init, activation, IAM/resources, image or customer action belongs to
this source change. The earlier dropped-update witness remains valid against
exact completeness; it is not a mandatory CDC prerequisite for recovery hints.
