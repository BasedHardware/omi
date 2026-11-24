# Durable projection follow-up discovery

The follow-up page re-reads persisted/ready results before process-local backoff
can reject them. `projection_followup_due_at` moves that scheduling hint into the
query, independently of the finish clock and assignment cursor. The unchanged
receipt, privacy, ledger, usage and completion transactions remain authoritative.

Only an async attempt that passed `read_persisted` and returned `incomplete` may
defer a row. The write re-reads the result transactionally and requires its entire
preimage to equal the validated snapshot. Concurrent state, receipt, privacy or
wake updates win. An already-future deadline is never extended by a stale replica.
The delay is `min(60, BATCH_PIPELINE_PROJECTION_FOLLOWUP_BACKOFF_SECONDS)` seconds;
it never escalates. Failures, privacy refusals, timeouts and claim contention do
not write a durable delay. Changes to dependencies outside the result may unblock
it without a direct wake; the fixed deadline bounds that extra delay to 60 seconds
plus normal discovery/queue latency. Targeted and owed recovery bypass the query.

All existing result-state writers stamp this independent clock due-now atomically
on entry to `persisted`/`ready`, and remove it on exit. The due cursor orders by
`projection_followup_due_at`, `committed_at`, document ID; ordering changes reset
the cursor. Each due pass freezes its eligibility cutoff until wrap, so new
arrivals cannot keep extending its tail and starve work behind the cursor.
Durable discovery replaces the process-local skip cache, so a state
move is not delayed by an older local snooze. Assignment and finish query paths
continue using their existing independent cursors/clocks.

## Deployment and schema admission

1. Merge the declared dev/prod result indexes and wait for normal index readiness
   admission. Deploy unconditional clock writers on **every** result-writing host
   and drain old writers. Release owns this operation. Source merge is insufficient.
2. Keep the legacy page while the version-1 follow-up marker is absent, false or
   unreadable. Negative marker reads are throttled to once per minute; unreadable
   markers record the shared fallback signal and leave legacy discovery active.
3. After proving writer coverage, the existing admitted operator runs the bounded
   stamp tool. It reads at most 200 rows/page, resumes a shared transactional cursor,
   preserves existing clocks and writes only missing scheduling hints. No row
   payload, receipt, privacy state or owner changes. Dry-run by default:

   ```bash
   python scripts/batch_pipeline_projection_followup_backfill.py --stage prod
   # Separate admitted prod-operator action, only after writer-coverage proof:
   python scripts/batch_pipeline_projection_followup_backfill.py --stage prod \
     --apply --confirm-writers-deployed --max-pages 10 \
     --page-size 50 --max-rows-per-second 10
   ```

   Apply defaults to a **10 newly admitted candidate rows/second** page budget,
   with one page-size burst. One monotonic limiter spans the entire invocation;
   waiting occurs before page reads or transactions, never inside a transaction.
   Every page reserves its full configured size, including a short or empty page,
   so it cannot exceed the candidate-admission budget. Slow IO earns no catch-up
   credit. A restart or second driver has an independent budget: this is not a
   distributed lock. Release designates one driver; the operator identity gate
   and transactional checkpoint preimage check reject a stale concurrent page,
   rather than implementing a singleton lock. Pacing waits print counts-only
   progress on stderr at least once per60-second sleep chunk.
   SDK transaction/RPC retries are **not separately rate-limited** by this page
   budget; observe the admitted Firestore abort/retry bounds and stop at a page
   boundary on a trip. Do not describe this as a physical billed-read/RPC ceiling.
   A lower value changes operator throughput, not a serving parameter. Dry-run
   remains one unpaced page and is not a no-row-read aggregate operation.

   Each page and checkpoint commit atomically. A concurrent cursor change fails
   the page rather than advancing stale progress. Prefer one admitted multi-page
   invocation. Between bounded invocations, wait at least `page-size / rate`
   seconds AFTER the previous invocation finishes (5s for the example), using
   only one driver and no catch-up, until `complete:true`. A fresh invocation's
   first-page burst does not otherwise preserve the prior process's rate budget.
   No production migration is authorized by this runbook.
4. The default-on reader begins after the same namespace's versioned completion
   marker. There is no permanent default-off cohort. First read `durable_deferred`
   outcomes and native/caller reads **and writes**, progress, delay/age and failures;
   require a complete post-overlap observation hour before booking any savings.

`BATCH_PIPELINE_PROJECTION_FOLLOWUP_BACKOFF_SECONDS=0` is the immediate kill switch:
legacy discovery and existing recovery work remain. Do not reverse backfill or
rewrite receipts. Turning page selection or pagination off also uses the legacy
path. Writer clocks stay unconditional, so rollback/re-enable preserves coverage.
Before reverting to pre-clock writers, first roll readers with backoff=0 and
prove the previous due-filtered readers have drained. Keep that legacy reader
mode throughout writer rollback. Do not reuse the old completion marker after
such a downgrade: re-enabling requires an operator-reviewed fresh marker/pass
and complete writer coverage. The tool intentionally does not silently reset a
completed marker while live readers may have cached it.

## Scope and evidence

No changes to privacy admission, retention, provider release, worker deployment,
finish classification limits or assignment/completion semantics. The measured
follow-up caller pool contains useful work and is not a savings forecast. Assess
net economics after backfill/defer writes and overlapping rollouts. Real emulator
coverage is in `tests/integration/test_batch_projection_followup_clock_firestore.py`;
hermetic guards cover race rejection, migration and discovery mode transitions.

## Read-budget planning envelope

The collection budget reserves 200,000 marker reads/day for a planning fleet of
100 processes checking an incomplete marker once/minute plus 10,000 admitted
backfill pages/day with up to four marker reads/page (retry and shadow refresh).
For those pages, 200 rows/page and six reads/row reserve 12 million migration
reads/day: discovery, transactional fence and optional shadow refresh, with one
retry. These are planning bounds, not a measured fleet, population, spend or
runtime cap. The operator must remeasure/rebudget before exceeding the envelope
or repeating passes/retries beyond it. In particular, a50-row page at10rows/s
could admit17,280 pages/day if run continuously, exceeding the10,000-page marker
budget. The example is a bounded10-page pilot, not permission for continuous
restarts; either stop at the admitted daily page bound or obtain a rebudgeted
packet. Normal serving never invokes stamping.

## Store protocol parity

Postgres and simulation adapters implement the same independent clock/cursor
interface and read their own native versioned control marker. Firestore marker
completion does not qualify a Postgres primary or authorize native clock
activation; its existing owner retains native population/index/authority gates.
No native Postgres backfill or activation is added here. Serving-parity marker
observations use the existing bounded connection without a serving transaction
or row lock. These adapter obligations do not add a gate to the Firestore rollout.
