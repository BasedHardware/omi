# Commit-triggered batch projection

`BATCH_PROJECTION_OUTBOX` resolves to `true` when unset in Python, including
when `CAPTURE_COVERAGE_MODE=serve`. With the switch enabled, normal merge and
source-alias fallback atomically stamp a due obligation on the existing result
document. The segment ID and immutable owner log sequence identify a commit. Release and privacy
resume can rearm that slot in their existing transactions and invalidate a
previous claim. The scheduling fields contain no transcript, audio reference,
conversation identifier, or billing state.

Serving enqueues a bounded in-process hint after its commit succeeds. Hints use
up to half the queue, leaving room for the elected scan to recover missed wakes.
The GPU pump has no projector. Its stamped commits are found by the elected due reader
through the same index that recovers lost serving hints. The `ef42ee8` GPU
image and earlier backend writers produce unstamped results. All legacy
assignment, finish and follow-up readers still cover them.

The outbox supervisor starts on a batch-serving or dedicated projection pump
process whenever the outbox switch is on. A batch-serving process continues
outbox discovery with the legacy projection sweep disabled. This keeps the
projection and first-summary policy stamps on their owning serving roles.
All scanners share one strict `projection_outbox_scan` lease per namespace. A holder confirms its
token after reading a bounded `kind, due_at, document ID` page. Loss of the token discards
the page. Already-admitted delivery has its own 180-second claim and can finish
through a leadership change. A crashed worker leaves retryable debt at claim
expiry. Claims and settlements modify only scheduling fields on an existing
result. The existing assignment, privacy, ledger, enrichment and accounting
fences apply separately on every attempt. Legacy and outbox follow-up workers
share the existing process-wide follow-up slot budget.

The consumer defers predecessor, claim and Firestore transaction contention for
10 seconds and retries other unfinished assignments after 60 seconds. For
persisted or ready receipts, it honors a future `projection_followup_due_at`.
Other unsuccessful finishes use the configured follow-up backoff, with a
60-second retry when that setting is zero. Outbox settlement owns this retry
clock. A pending predecessor also uses the existing owner replay path, which
can find unstamped commits from older writers. A ready multipart receipt can
still owe work for siblings. Only canonical completion settles it as completed.
A durable quarantine parks the obligation for the existing held/release owner.
An expired claim on a completed result settles from the result state without
replaying publication or accounting. Privacy purges retain their existing
ordering-edge or deletion behavior and scheduling fields follow result retention.

Claim tokens fence scheduling updates and acknowledgements. The canonical
projection session also validates the token when it reads the result inside its
transaction, and the outbox rechecks it after accounting and before the Redis
fair-use call. In-flight external calls rely on the existing idempotency keys.
Binding, ordering, privacy, receipt and ledger checks still govern canonical
mutations and replays.

## Compatibility and release

| Deployment role | Dev | Staging | Prod |
| --- | --- | --- | --- |
| Cloud Run backend and backend-sync | `true` | `true` | `true` |
| Cloud Run backend-integration and backend-sync-backfill | `true` | `false` | `false` |
| Dedicated Cloud Run projection pump | — | — | `false`, inherited from integration |
| GPU batch worker | `true` | — | `false` on main and T4 |
| GKE backend-listen | `false` | — | `false` |

These are source settings. Check the running image source and resolved
environment before assessing a production pin’s effect. The dedicated pump is
dark and has its own activation order under SCA-3318. Its pump selector and the
outbox switch control different behavior.

Listen runs the shared backend app. Its batch recovery and commit-wake routes,
and the provider STT settlement hook, can enter the shared ordered merge path.
That path can stamp obligations and invoke request-driven legacy projection.
The elected outbox scanner needs batch serving or the dedicated pump enabled.
Listen’s chart leaves batch serving off and the pump selector defaults off.

- A live lease and a due query that succeeded recently and is keeping up
  certify the backstop. The mark expires within 30 seconds of a stalled scan.
  A row needs its own valid obligation before a compatibility page skips
  policy lookups and projection transactions. No fleet-wide completeness
  assumption, writer backfill or committed-time cutoff is used.
- Older projection binaries can consume any result through the same durable
  receipt and accounting fences. Older reactivation writers can leave no active
  obligation. These rows remain visible on the legacy pages. An updated writer
  with the switch off clears the previous due time and claim on a reactivated
  row, so readers that still have the switch on leave it to legacy discovery.
- Follow-up due-clock coverage and its marker retain their own admission.
  #25314 still classifies async finish receipts. The #25596 overlap observer
  continues to count every returned legacy follow-up row, including those
  subsequently skipped. #25555's keyset parity holds on the raw page and
  #25623's refused-head disposition stays with the canonical projector.
- Before enabling any participating writer or reader, verify both
  stage-specific Firestore composite indexes are READY and confirm the due
  query. For each writer, verify eligible commits stamp obligations and a
  qualified reader covers them in the same namespace. For each reader, verify
  claim and settlement and compare matched completions, partial latency,
  oldest obligation age, failures, and read and write telemetry across the
  actual serving roster. Exercise legacy discovery with older and off writers.
  Apply both checks to roles that write and read. The doc-mode Postgres adapter
  mirrors due selection for qualification. Firestore remains the serving effect store.
- Production changes require a separate Release order naming roles, settings,
  canary and rollback. Read back the effective settings on the serving roles.
- Rollback sets `BATCH_PROJECTION_OUTBOX=false` on the relevant readers and
  writers. Assignment, finish and follow-up discovery proceed on the original
  result and receipt state. Keep the scheduling metadata and result retention.

## Read and write accounting

Result-row stamps add zero document writes to a merge transaction. A delivered
row normally adds one claim and one scheduling settlement, inferred at about
3.03 million writes per day at the design record's 1.516 million daily commits.
Retries, index-entry maintenance, scan leases and coverage reads add cost. Earlier binaries'
compatibility pages still return stamped documents, and new readers also pay
for raw pages. The avoided work is the downstream policy, assignment and
follow-up probing of covered rows, particularly while their due time is in the
future. Production net savings are unmeasured.

Keep the existing oldest-unfinished projection gauge on the full result view.
For release qualification, compare matched read origins, writes, completed
units and audio, projection age, partial latency, and transaction failures
across the full writer/reader roster. The local outbox outcome counter
`omi_batch_pipeline_projection_outbox_total` uses bounded disposition labels.
