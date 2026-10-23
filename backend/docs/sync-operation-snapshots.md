# Sync operation snapshots and remaining transaction work

`SYNC_OPERATION_SNAPSHOT_ENABLED` defaults on. Set it to `false`, `0`, `off`
or `no` to restore the previous redirect hydration and no-effect bridge reads.
It is independent of the reads loop's cohort levers; this change does not edit
their configuration.

An owner read following a sync redirect still checks each hop's deletion marker,
stored owner and stored id, and retains the cycle and 16-hop guards. Its final
raw conversation snapshot carries Firestore's update time into the ordinary
photo and transcript decoding path. Hydration no longer fetches that same
survivor document again. The snapshot is local to the call, the decoder takes
a detached copy, and mutations keep their existing transaction reads and CAS.
The redirect helpers accept a keyword-only `firestore_client`. Each redirected
read selects one client lazily and uses it for resolution, both hydration modes
and photo reads; invalid paths are rejected before client initialization.
First-summary outbox custody still resolves only an id and transfers its
obligation transactionally; no snapshot passes into the next delivery.

Bridge traversal reuses its initial survivor metadata only when it has no
donor lineage and attempts no effects. Reading a donor also forces the final
refresh, so a redirect or deletion during ancestry traversal is observed.
Reuse requires the existing `backfill_task_reads` metadata-only path; the
legacy hydrated reader retains its refresh after photo/correction IO. This PR
does not change that lever or its cohort.
Transfer, retraction, audio copy and receipt writes each force the
existing final refresh, including failed or deferred effects. A new traversal
starts fresh. No transcript, speaker, cap, hold, deletion marker, entitlement,
polling or privacy-authorization logic changes.

Both modes attribute their reads to the constant origin
`job:sync_operation_snapshot`. The counter
`omi_sync_operation_snapshot_reads_avoided_total` has that same `origin` and
`operation=redirect_hydration|bridge_no_effect`; one increment represents one
redundant lookup avoided. It is an algorithmic count, not billed fleet savings.
The focused fake tests count actual document gets and compare decoded content,
compressed stored bytes, access outcomes and post-effect refreshes.

Redirect hop reads now have caller
`sync_conversation_snapshot:resolve_snapshot` instead of the old
`conversations:resolve_sync_conversation_redirect` / raw-snapshot split.
Their label movement is not a saving. Keep that caller in the reads loop's
post-deploy baseline and use the fixed origin plus avoided-read count to avoid
grading a vanished old caller as eliminated work.

The report's P5 22M/day is a planning ceiling across raw snapshots, redirects,
assignment and Typesense. This bounded change saves one read per successful
redirect hydration and one per bridge traversal with no lineage or effects.
Its daily prediction is the measured count of those two events, with coverage
and operation mix checked against the origin's billed-equivalent reads. Do not
book 22M/day or add it to another lever's saving. Equal 24h windows, the served
SHA and D+2 billing remain the production acceptance criteria.

## Index projection: contract decision required

`ProjectionIndex` already coalesces canonical ids and donor deletes by owner
before `index_sync_assignment` loads current durable index fields. Preserve
those post-commit loads and the live E2EE eligibility check. Assignment output
cannot replace them across the commit/deferral boundary: an edit, deletion or
redirect can win before the index flush.

The existing enrichment outbox (`database/outbox_firestore.py`) explicitly
requires content-free payloads of at most 4KiB. `structured` contains user
content and is unbounded relative to that limit. It must not be copied into
that outbox. An index obligation can instead carry only a conversation id and
writer generation. Its consumer must load current content once, check current
eligibility, and publish under the current generation; all index-affecting
writers must atomically re-arm it, and deletion/policy writers must invalidate
or purge it. Adoption requires an all-writer inventory, replay/CAS and
out-of-order delivery tests, a migration/rollback contract, and a measurement
of incremental writes versus eliminated repeated index invocations. Adding
that obligation without writer coverage would allow stale or missing search
results. No index migration or eligibility reuse is implemented here.

## P4 design only; after P5 and WQ12 remeasurement

Current assignment flow in `utils/batch_pipeline/projection.py`:

1. `ProjectionStore.check(session)` runs a read-only transaction through
   `ProjectionSession.prepare`.
2. Context/build/candidate discovery runs outside that transaction.
3. `assign_sync_conversation` starts a fresh transaction: `prepare`, assignment,
   `validate_plan`, and `persist` commit the transcript and receipt together.
4. Bridge and playback effects run outside assignment.
5. `mark_enrichment` rechecks binding and authority and atomically queues the
   obligation with its ready receipt. Completion/accounting and client
   publication have additional fresh transactions.

The successor walk already skips step 1 for a new receipt-free part. P4 should
first measure the residual non-successor prechecks after WQ12 settles, then
consider omitting only the redundant read-only precheck where step 3 already
enforces the same predecessor, binding, generation and ownership contract.
This moves rejection later, so measure wasted context/build/provider work too;
never treat discovery as authorized mutation. Empty and superseded paths must
keep their own transaction checks. Each retry must rebuild session and
authority snapshots, and size-limit retries must not retain a previous plan.

Steps 4 and 5 are distinct authority boundaries. Do not fuse them or carry
account/user/privacy/tombstone/hold decisions across them. Completion and
exact-once accounting also remain separate until a proof covers duplicate
delivery, retry, redirect, concurrent deletion, custody transfer and billing.
No P4 implementation or privacy caller change is included. Its 25M/day target
is conditional on residual phase counts; it cannot be summed with WQ12.
