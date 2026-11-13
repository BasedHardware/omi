# Dark jobstore mirror and serving parity (package C)

Source-only package for SCA-1807. Firestore remains the sole writer/claimant.
No production admission, live shadow evidence, serving readiness or savings is
established by this change. Source savings: $0.

## Rebinding and ownership

The accepted SCA-1683 design inspected `a55ae72b71f7af8d8e304a7631b913c9b1d1722b`.
This implementation starts at `faec7c5a72f5e7fc4eabda4916c7be767b66fb12`. The relevant intervening change is merged #23806's
`cancel_fenced_recovery` implementation; #25116's SQL composition is already
present. C changes mirror/admission/erasure/parity machinery, not the scheduler,
queue authority, reverse journal or reverse copier. SCA-1697 owns that D work.
The dated `phase2-scope.md` and pipeline-plan files referenced by the design are
not present in the fetched omi-workspace tree; the attached accepted design is
the available scope contract. Later shared-file changes require revalidation.

## Controls and erasure

- `BATCH_JOBSTORE_MODE=firestore` remains the default.
- `JOBSTORE_SHADOW_NAMESPACES` is a comma-separated list of exact namespaces;
  its default is empty. No wildcard admits a namespace.
- Admission never overrides L02-2: `batch_pipeline_prod` additionally requires
  `OMI_DEPLOYMENT=staging` and `FIRESTORE_DATABASE_ID=staging`. Production stays
  refused, including with an explicit namespace entry.
- `JOBSTORE_SHADOW_QUERY_PARITY=on` additionally opts into asynchronous serving
  comparisons. Defaults produce no additional serving-query traffic.
- `JOBSTORE_SHADOW_WRITES=off` stops new mirror work. Erasure remains synchronous
  and retryable with mode off, admission empty, or writes disabled.
- Retain the dedicated `JOBSTORE_PG_HOST/DATABASE/USER` target until its retained
  copies are retired. Partial configuration and missing drivers fail erasure;
  a database failure propagates to the deletion retry. Cached copies are also
  erased without configuration. No new connection is built when no target exists.

Deletion visits both dev and prod namespaces on the customer data plane; its
read-only erasure view deliberately does not use the stage-qualified serving
factory. It cannot run a write transaction. Existing per-key locks, namespace
purge barrier, retry semantics and second reconciliation scan remain in place.
The second scan is bounded legacy-worker coverage, not a proof against arbitrary
unfenced old binaries; D's all-writer inventory remains an activation gate.

## Census and query evidence

The census covers jobs, queues, owners, control, results, gpus, intakes, artifacts,
pull_claims and merge_holds. Successful Firestore claim CAS operations refresh the
cold copy; PG never acquires a shadow claim. Erasure reconciles owner-keyed merge
holds and the owner's shared pull-claim/control shard as well as linked rows.

`serving_parity.compare_serving_query` executes the actual PostgresStore read
methods and the actual PostgresTransaction reads, rather than parallel SQL.
It compares complete codec-normalized ordered results, documents, nulls and
cursors. An explicit method allowlist refuses mutation methods; point reads are
restricted to mirrored batch tables. Transaction comparisons never flush writes.
Firestore RPC retries and timeouts share one observation deadline with PG
connection acquisition and statements. Observers reuse only warm PG connections
and never initiate IAM refresh or connection establishment; a cold pool is an
error, not a pass. Expired observations cannot record a match. A broken transport
may still delay synchronous driver cleanup; the separate worker/queue contains
that delay and reports dropped observations as unknown. Two immediate observations
of each side distinguish changing pairs (`unknown`) from stable `match` or
`mismatch`; errors are `error`. All four outcomes have bounded query labels in
`omi_jobstore_serving_parity_total`. An unknown, dropped observation or error is
not a pass. Opt-in automatic observations use a separate bounded queue (a slow query cannot
delay document copying), honor the write kill switch, and preserve the
primary result. Transactional comparisons are explicit rehearsal calls; normal
transactional point-read mirroring retains its existing convergence tracker.

Record-pending observation uses the serving query's shared implementation with
recovery promotion disabled, so an observation cannot replay promotion writes.
Resumable conversation purge runs its cold-copy phase regardless of mirror mode;
PG failures leave its obligation incomplete for retry.

The real emulator/PG matrix covers every enumerated read, empty/populated
fixtures, ties, duplicate successors, null versus missing previous links and
ready clocks, inclusive/exclusive cursors, deliberate PG drift, mode-independent
cold-copy erasure, claim copying, owner-serialized phantom protection and existing
retry/contention/custody goldens. Frozen fixtures require exact equality.

## Gates that source cannot satisfy

`repair_lineage` remains deliberately Firestore-only in the dark mirror: it
contains capture claims/geolocation and the existing mirror does not follow the
intake receipt TTL (#24366). No authoritative PG store is introduced here; D
must retain required lineage under the correct privacy/retention contract before
serving. Whole-document comparisons do not silently normalize that omission in
the new serving checker: an intake point comparison with lineage will mismatch.
The existing document census's normalization is not full-field serving proof.

Immediate query rechecks do not certify the design's ten-second live convergence
window, per-method traffic minimums, 24-hour full-field gate or staging sizing.
The existing conformance adapter uses synthetic customer state for PG; it does
not prove cross-store privacy serialization. Reverse-copy/epoch fencing,
production namespace approval, L02-2/restart, RC2, real privacy races, end-to-end
capture acceptance and settled billing remain separate gates. Keep serving dark.

The generic Firestore enrichment outbox adapter has five existing conformance
failures at this base (wake timing/coalescing and wake-create exception behavior).
They are reproduced against the unchanged base and left visible, with the suite's
existing skips and strict xfails; they are not converted into passes or hidden.
