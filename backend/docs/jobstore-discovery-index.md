# Firestore-authoritative discovery index preparation

`BATCH_JOBSTORE_MODE=index` wraps the existing mirror with a non-authoritative
discovery reader. Firestore still performs every transaction, lease, claim,
privacy check and state change. Default mode remains `firestore`.

This source is dependent on dark-mirror PR #25323. Production factories require explicit target/context configuration; all copies
enforce the resolved-owner cohort. Release activation and savings still need
the production runtime acceptance packet.
See [production mirror prerequisites](jobstore-production-mirror.md).

**Production reader admission is currently refused.** Production copies are
owner-sampled, but `Scheduler.recover()` calls an unpartitioned `due()` query.
This source has no complete-query coverage proof or owner-partitioned primary
caller. `IndexStore` therefore returns Firestore answers with reason
`coverage_unknown`, including after a successful primary scan and even with
the owner-copy sample at 10000 BPS. The same check runs before returning an
index answer if deployment context changes. Staging keeps its existing route.
This is a source prerequisite, not reader-canary readiness or activation.

## Selection and rollback

The existing namespace admission and complete `JOBSTORE_PG_*` configuration
are required before constructing a mirror or index wrapper. Index selection
adds two controls:

| Control | Behavior |
| --- | --- |
| `JOBSTORE_INDEX_QUERIES` | Exact comma-separated query names; default `due_leased`. Empty or any invalid name returns discovery to Firestore. |
| `JOBSTORE_INDEX_READS` | Default on; `0`, `false`, `off` or `no` returns discovery to Firestore. |

Supported names are `due_leased`, `due_retry` and `due_result_ready`. These
callers recheck the discovered job or merge owner through existing Firestore
transactions before acting. `record_pending`, `control_candidates`, fresh
ordering probes, cursor pages, completion markers, gauges and capacity/spend
decisions remain on Firestore. An empty index answer must never release a
hold, finish a drain or backfill, or authorize lower-priority work.

The controls do not override the production coverage refusal. Setting a
reader flag or splitting HTTP traffic cannot partition background recovery.

`JOBSTORE_SHADOW_WRITES=off` also disables index discovery. Both kill paths
are rechecked before returning a Postgres answer; an existing wrapper falls
back if its allowlist changes. Roll back through the release owner with
`JOBSTORE_INDEX_READS=off`, or select `shadow`/`firestore` mode. Retain the
copy target and synchronous erasure access while any copies remain.

## Discovery and failure behavior

Each selected query starts with a canonical Firestore read and repeats that
read after a successful-primary-scan interval. The source default is 60
seconds, measured separately for each query. Factory caching preserves this
state across repeated store construction. A failed Firestore safety read
raises; it cannot silently become an index answer.

Each safety read returns the existing bounded due prefix, at most 100 IDs.
This interval is not a guarantee of complete backlog discovery. A permanent
prefix blocker can retain the primary's existing starvation behavior; dropped
copies beyond that prefix need the coverage/retirement work in the production
packet. Measure the deployment's freshness before selecting an operating
cadence or ramping a query.

Between primary reads, the index reuses the Postgres store's due SQL, ordering
and limit. It uses only a warm pooled connection, a read-only transaction,
server statement timeout and a synchronous driver-wait deadline. No IAM
refresh, connection establishment or timeout worker runs on the discovery
path. Postgres failure or timeout discards the connection and uses Firestore.
Primary fallback can still take its normal bounded RPC path; the index read
budget is not an end-to-end primary-request latency promise.

## Evidence and release sequence

`omi_jobstore_index_reads_total` records bounded query/source/reason/outcome
labels. It counts returned discovery answers, including empty answers, and
errors; it does not count billed rows or prove work completion. The batch
worker's private registry includes it in index mode. Optional
`JOBSTORE_SHADOW_QUERY_PARITY=on` still queues comparisons on the mirror's
bounded asynchronous observer, including after index answers. An error or
dropped comparison is unknown, never a match.

`omi_jobstore_index_primary_scan_success_timestamp_seconds{namespace,query}`
is the Unix time at successful completion of an actual primary `due()` call.
It advances for safety, disabled, unselected, coverage-refused and recovered
fallback primary answers, including empty answers. Failed primary calls, PG
answers, parity enqueueing and scrapes do not advance it. The monotonic clock
still controls the unchanged 60-second per-wrapper sweep cadence; wall time
is used only for evidence. A newly constructed wrapper still reads primary
first. No label series is created merely by construction or collection.

Namespace labels are bounded to `batch_pipeline_dev`, `batch_pipeline_prod`
and `other`; query labels are the three admitted names. `other` cannot certify
a runtime scope. No owner, job, cursor or customer content is a label. The
batch worker's private registry exports the same gauge in index mode, including
when reads are killed. Absence, a future timestamp, stale scrape or missing
caller/leader binding means UNKNOWN, never a fresh scan. Gauge age is
`time() - omi_jobstore_index_primary_scan_success_timestamp_seconds`, evaluated
for the actual caller/namespace/process. Bind the active recovery leader and
its succession; idle replicas do not owe recovery scans, and a fleet `max`
can hide a stale active caller. Do not combine unrelated namespaces, retired
leaders or revisions. With a running caller, allow at most the 60-second
cadence plus its measured invocation and scrape delay; this is not a timer
that performs scans when the caller is idle. Neither this gauge nor a returned
bounded prefix proves complete backlog coverage.

## Coverage prerequisite and first read-removing route

The current owner-copy selector is
`int(sha256('omi:jobstore-production-mirror:v1:' + owner_key), 16) % 10000 < BPS`,
with an explicit ASCII integer BPS in 1..10000. At 100 BPS it selects 100 of
10000 owner hash buckets, stable across replicas/restarts. It does not select
1% of jobs, calls, rows or cost. At 10000 BPS malformed/unknown owners still
remain outside the copy. Sampled-prefix parity and reconciliation cursor
passes do not certify the full evolving due population.

The smallest complete-query route starts with `due_leased` only. It needs a
reviewed producer/coverage prerequisite outside this index-only change:

1. Bind the primary query scope and retained copy target, source version,
   producer roster, erasure paths and coverage generation. Either cover every
   potentially leased row in that namespace (including any currently omitted
   ownership class), or add a genuinely partitioned primary caller and matching
   PG predicate. A 100-BPS copy cannot replace the existing global query.
2. Establish complete admitted population coverage with zero missing,
   excluded or unknown relevant rows, complete writer catch-up and bounded
   retirement/erasure lag. A census alone while writes run is insufficient:
   the coverage generation needs a reviewed writer fence/catch-up boundary,
   expiry and invalidation on roster, target, cohort or source change.
3. Only then implement admission that checks that proof live before and after
   SQL, alongside the existing kills. Unset, invalid, stale, revoked or unknown
   proof must return the same full Firestore answer. No env boolean is a proof.

A concrete future reader sampling contract to review with that prerequisite
is SHA256 of `omi:jobstore-discovery-reader:v1:` followed by compact ASCII JSON
`[namespace, role, query, floor(unix_time / 60)]`, interpreted as an unsigned
big-endian integer modulo 10000, selecting buckets `< 100`. The semantic role
is `pump_recovery` or `serving_maintenance`, never a random lease-holder ID.
Its unit is **eligible caller-minutes**, with a common UTC epoch, never replica
ID, process randomness or restart time. All replicas and restarts agree for
the same role/minute. Unselected
calls still execute the full primary query; selected calls may use PG only
with complete coverage, after the first primary read and within the safety
interval. This is a proposal, not an implemented selector: no new percentage
flag is added here. Time buckets do not promise exactly 1% of calls or reads;
actual selected-call and read counts must bound exposure before expansion.

For this head, eligible production PG calls are **0**: every production due
call uses Firestore. The measurable denominator `N` is instrumented
`IndexStore.due()` invocations for the bound query/roster/window, using the sum of
`omi_jobstore_index_reads_total` over sources/reasons/outcomes. Each completed
invocation records one terminal answer or primary error; a PG error followed
by a successful primary answer counts once here and separately in shared
fallback telemetry. Factory bypasses (Firestore mode or an empty/invalid
query allowlist) are outside this counter, so it cannot establish an all-caller
denominator across those modes. That requires caller-entry instrumentation
before factory routing. This is a call denominator, not scanned/billed rows,
distinct jobs or audio-hours. A future selector needs separate eligible and
selected counts; PG-return counters alone cannot establish its denominator.

Root and Release own the earliest eligible `due_leased` slice (target November
18, 2026). This source does not admit a slice with missing coverage. Expansion
to retry/result-ready needs actual counts, parity, SLOs, a full predeclared
new-state lookback and two fresh scrapes. Final PG authority/G2 GO remains
separate; there is no dependency on D. Reader inverse: `JOBSTORE_INDEX_READS=off`
and `BATCH_JOBSTORE_MODE=shadow`, then verify primary answers for the same
caller. Preserve target and erasers until retained-copy obligations end.

Production sampled-prefix parity uses distinct `due_leased`, `due_retry` and
`due_result_ready` query labels. It checks selected primary-prefix coverage and
every returned hint against current primary documents; it does not claim
whole-backlog equality. Record the selector/source and state-specific route
traffic alongside this proof. Other sampled discovery comparisons are UNKNOWN. Include mirror rereads and parity/census
overhead when measuring net Firestore reads.

The release owner first completes mirror cohort enforcement, copy retirement,
erasure and writer-version coverage. Then validate one selected poll in the
synthetic/staging matrix, including dropped copies, stale hints, timeout,
kill-switch and mode-off erasure. Prepare a source-pinned production ramp of
leased, retry, then result-ready reads, with expansion owned by the existing
SCA-2288 release owner at the next evidence review after each query's gates
pass. Record that review deadline in the release packet before activation.
There is no artificial soak interval or implicit expansion from source merge.

Runtime acceptance needs the actual serving release identity, relevant query
traffic, correct transactional actions, measured primary-sweep freshness,
parity and rollback evidence. Settled savings remain the cost owner's separate
billing claim. Current local tests establish source behavior only.
