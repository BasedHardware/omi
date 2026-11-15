# Firestore-authoritative discovery index preparation

`BATCH_JOBSTORE_MODE=index` wraps the existing mirror with a non-authoritative
discovery reader. Firestore still performs every transaction, lease, claim,
privacy check and state change. Default mode remains `firestore`.

This source is dependent on dark-mirror PR #25323. Production factories require explicit target/context configuration; all copies
enforce the resolved-owner cohort. Release activation and savings still need
the production runtime acceptance packet.
See [production mirror prerequisites](jobstore-production-mirror.md).

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
