# Sweep admission, source selection and deferred unlock replay

## Deployment boundary

The operator supplied these deployment observations on 2026-09-18; they were
not independently queried during this change: production has never deployed
a daily sweep job; dev has an hourly scheduler and a manually dispatched QA
job, with no executions running at the observed checkpoint. Thus production's
first sweep deploy can use this identity exclusively. Before the dev transition,
pause the hourly scheduler, stop manual dispatch, and retain execution-status
evidence that **all pre-lock executions have terminated**. Deploy both jobs
before resuming either source of execution. No legacy-ID tombstone is written.

The job additionally runs `assert_no_live_pre_lock_claims` for its bounded UID
inventory before scheduler work or inventory acknowledgement. It reads at most
10,001 projections using the single-field `claimed_at` range index, examines
`pending` claims within the existing 15-minute invocation lease, and rejects
claims without `admission_id` with `pre_lock_claim_live`. The uncaught exception
makes the job fail nonzero. Operators keep the scheduler paused, terminate/drain
old executions, and retry after the latest old claim's 15-minute lease ends.
Do not erase fences. Expired claims fall out of the query automatically;
`pre_lock_scan_over_budget` instead requires checking the recent claim volume
and retrying after that bounded time range has drained. Pre-lock writers always
store `claimed_at` and do not renew this lease.

**This assertion cannot observe an old worker paused before its first claim.**
Only the deployment drain above protects this one transition. The hermetic
counterexample deliberately demonstrates that a pre-lock claimant with digest A
can dispatch after a new worker selected digest B. New admission cannot retrofit
an admission read into an old binary. Deployment evidence is required; a green
preflight alone is not that evidence. There is no claim of a transactional
barrier against pre-lock code, and no remote rollout was performed here.

## Permanent admission and dispatch state machine

Every generation-fenced model entrypoint first transacts on
`daily_memory_sweep_window_admissions/H(uid, account_generation,
source_generation, sweep_generation, window_id)`. The hash domain
`daily-sweep-window-admission.v1` and this key contract are permanent across
future invocation-identity versions. Onboarding's window also contains its
server-owned source key. Selection, text and version-specific invocation IDs
are absent from the admission key.

The admission transaction checks account deletion and live generations. It
reads the prior lease and commits the identity tuple, a random holder token
and a 15-minute deadline before evaluating any invocation identity factory.
After that commit, the holder computes the first invocation ID and binds it
in a second transaction that rechecks deletion, generations, holder token and
lease. A crash before binding leaves only a leased unbound admission; because
no invocation could have been claimed yet, the next holder may compute its ID. The invocation binding is
durable; lease expiry or release NEVER deletes/recomputes it. New acquisitions
reuse it even if the new binary's identity factory would return something else.
Active overlapping holders return `window_admission_busy`. A token-bound
release runs after invocation completion/failure; a crashed release waits for
lease expiry. Admission records are content-free and retained alongside the
top-level invocation fences, including across recursive user deletion.

The subsequent invocation claim transaction writes the same invocation ID,
`admission_id`, owner/generations/window, `input_digest`, random `claim_id`,
`pending` state and release count to the top-level fence and user payload.
Deletion/generation checks still run inside claim, result and canonical apply
transactions. Once dispatch may have happened, `pending`, `indeterminate`,
`returned`, expired payloads and exhausted releases never mint a new identity.
Only certified pre-dispatch failure releases the exact claim, at most
`MAX_PRE_DISPATCH_RELEASES` (3) times. That path may select new input, under the
same admission binding. The staged candidate digest remains bound to the
claimed input digest and exact ordered output page.

This handles late inserts, deletion of a selected row, summary edits and
unstructured-to-structured enrichment identically: selection may differ, but
invocation identity cannot. A changed input fails with `invocation_input_changed`;
a returned fence without valid retained output reports
`invocation_output_unavailable`. Pending and indeterminate claims have separate
`invocation_pending` / `invocation_indeterminate` reasons. Payload expiry reports
`invocation_payload_expired`; exhausted certified releases report
`invocation_pre_dispatch_exhausted`, including when the input has changed or
the expired user payload has been removed. An existing pre-lock
fence found by the bounded historical lookup reports
`historical_invocation_unresolved`. These are allowlisted content-free tokens.
Onboarding now uses stable source/window/generation ownership and a separate
input digest too, closing its returned-output/stage-gap transcript-edit defect.
An account/source generation change admits a legitimately different invocation;
stale workers cannot finalize or apply it under the new generation.

## One operator exit, using existing repair attestation

The existing repair function and QA repair CLI also accept:

`ATTEST_WORKER_TERMINATED_AND_ABANDON_WINDOW`

Use it as `--attestation-confirmation`, together with the existing
`--authority` and `--attestation-reference` arguments. It records
`operator_attested_skip_window` through the same receipt schema, identity,
claim ID, claim timestamp, operator identity and evidence-reference validator
as `operator_attested_no_dispatch`. The assertion explicitly accepts losing
this window's output and asserts that its worker has terminated; it does NOT
assert that the prior provider never ran. The receipt explicitly records
`window_disposition=abandoned`, `provider_dispatch_status=not_attested`, and
`accounting_checked=false`; it omits `attempts` entirely. No empty attempt list
is fabricated from unread accounting. The old misleading assertion is rejected. The lease plus the existing two-minute
repair margin must have elapsed. Returned claims are skip-only; the no-dispatch
assertion cannot reopen them. The operator list includes returned records so
stage-gap owners can be found; listing is not permission to retry them.

The producer consumes the receipt once, transactionally checking live deletion
and generations, and changes the exact fence to `window_skipped`. Subsequent
attempts reuse that empty outcome. The ordinary immutable packet and fenced
cursor pipeline then advances without invoking the skipped source again;
independent onboarding/day sources retain their own invocation fences. This works for historical
fences as well as window-keyed ones and does not adopt lost provider output.
The invocation retry path explicitly refuses to interpret a skip receipt as
permission to dispatch. Repeating the repair cannot create another receipt.
If old digest-keyed code already created multiple owners, use the same skip
command for each exact claim. The producer consumes their receipts in one
transaction only when every owner is attested or already skipped; an assertion
for one claim cannot authorize another. The lookup is bounded at 100 owners
plus one overflow probe, with at most 200 writes. Overflow remains fail-closed;
this is not an unbounded historical repair scan. No extra alias fence or second
repair mechanism is introduced.

## Locked content: shipped behavior and deferred gap

Locked rows are excluded before provider input and counted in
`locked_rows_excluded` without IDs or content. The day completes, including
complete-zero, and the cursor advances so free-tier users do not stall.
**A day consumed while locked is not revisited after a later paid unlock.**
Closing this rarer correctness gap is deferred to a separately reviewed PR.
`database/conversations.py` matches `origin/main`; payment, conversation,
memory and action-item unlock paths have no sweep metadata dependency.
No generation bump, cursor rewind, replay handoff or replay-specific canonical
write policy is shipped here.

For completed-day agent calls, every actual provider boundary re-reads only
`is_locked` on the selected source IDs, including before phase B. Missing rows
or failed reads report `source_lock_check_unavailable`; locking reports
`source_locked_before_dispatch`. Input is never silently replaced after claim.
Before phase A, the instrumented agent can certify failure and release the
claim under the existing bounded policy. After phase A dispatched, a failed
phase-B check leaves the invocation indeterminate and cannot permit another call.
Legacy rows with no `is_locked` field remain readable, matching other readers.
This costs one additional document read per selected row per provider phase:
at most 200 per phase / 400 across two phases in production, or 8 for QA's
single phase. Projections reduce payload, not billed reads. No new index is
needed for direct document reads. The check narrows but cannot eliminate the
check-to-call race: a lock can commit after its row's last read and before the
request is sent. There is no transaction spanning Firestore and the provider.
Onboarding retains its source-read lock check; its separate extractor does not
use the instrumented daily-summary provider boundary.

## Deferred paid-unlock replay design (not implemented)

The prior proposal correctly identified that a source-generation bump alone
preserves the completed-day cursor. Replay needs both generation-scoped ownership
and durable scheduling of affected days. It also requires an atomic publication
point that prevents the sweep from seeing a partial unlock epoch. The removed
implementation published each 100-row chunk separately; with 101 rows that
can dispatch one day in successive generations. It cannot be used as-is.

A follow-up should start from a durable, resumable unlock operation, with
idempotent batch progress and **one** final activation after every batch completes.
Payment success and sibling memory/action-item unlocks must not depend on sweep
metadata. An already-subscribed retry must be able to finish partial conversation
unlock after a crash. Invalid user timezones must be validated or resolved by a
server-owned fallback without aborting paid unlock. Deletion and generation
checks belong at the final activation and every later write. Coalesce overlapping
unlock operations rather than publishing repeated replay generations per batch.

Record affected local days, not a rewind through every intervening day. A
single year-old row must not cause a year of repeat provider calls. The design
needs an explicit aggregate replay budget as well as the existing per-run drain
limit (3 days per user, 1 in QA; 32 candidates and 16 canonical writes per day).
The durable queue, coalescing and overflow disposition need review before any
new generation can become visible. Missing/string start dates need an explicit
policy; the timestamp range alone cannot schedule those rows.

Preserve old summaries, packets and stages as provenance; never restamp them
into a new generation. A replay artifact should identify its predecessor and
have one logical owner, with old pending work explicitly invalidated at activation.
The earlier proposal kept UI summary documents unchanged and created new
memory-extraction stages; regeneration of UI summaries belongs to that writer's
update contract. Canonical provenance must distinguish replay from current
knowledge. Skipping an occupied subject/slot avoids overwriting newer or
user-authored facts but also loses historical corrections; an explicit recency
and conflict policy is required. These cache, stage and canonical policies are
design questions for the follow-up, not hidden behavior in this branch.

## Source observation and cost bounds

The `started_at` timestamp range uses the existing ascending index, ordered by
`started_at`, then document ID. No composite index is added. Its five-field
projection reads at most 100,001 documents, including one overflow probe.
The 2,000 ceiling now counts eligible rows only; discarded/locked rows do not
cause `eligibility_scan_over_budget`. A genuinely unexhausted 100,000-row scan
returns `source_scan_over_budget`, since unseen eligibility cannot be proven.
The higher scan ceiling accommodates 2,001 discarded/imported records and
roughly one recorded row per second for an entire day; it is a protective
engineering ceiling, not a measured assertion that no real account can reach it.
Projections reduce transferred data, **not billed document reads**: worst case
is 100,001 billed reads and zero full reads on overflow. A successful scan
uses at most 100,000 projected reads plus 400 full reads (16 in QA). It is not
appropriate to price those 100,000 projections as one cheap query. Eligibility
overflow is checked before any full-document reads.

Eligibility is an observed-read proof, not a stable snapshot. Projection and
full-document reads are not atomic. A processing mutation beyond the full-read
page or a later insert is not rechecked. Selected rows can change after reading; the dispatch-boundary lock re-check
above narrows privacy exposure without claiming an atomic whole-window view. There is **no explicit settle margin**: yesterday becomes eligible at
local midnight, potentially immediately after its end. Missing/string-typed
`started_at` values are outside the timestamp range, and attribution is by
start day, not finish day. These pre-existing limitations remain explicit.

`rows_seen` counts eligible projected rows; `rows_used` counts selected rows.
Contentless eligible rows increment `contentless_rows_omitted`, set truncation
and use that named reason when no stronger budget reason applies. Empty speaker
labels are not transcript content. Locked exclusions are a separate count.
Individually oversized rows are always skipped, including after a selected row;
an exactly-full page alone is never proof of truncation. Source evidence lives
outside the dictionary the real agent clears. Scheduler and receipt reason
fields use `SOURCE_REASON_CODES`; unknown values become `unknown_reason`.

## Local verification (Round 5, 2026-09-18)

Rebased onto the locally available `origin/main` at `591d701323` without
network access. No fetch was performed, so remote freshness was not independently
verified. `database/conversations.py` is byte-for-byte identical to that base;
`routers/payment.py` has no diff from it. The shared venv was execute-only.
Every Python command used `GOOGLE_APPLICATION_CREDENTIALS=/nonexistent/adc.json
CLOUDSDK_CONFIG=/nonexistent timeout 900` and `backend/.venv/bin/python`
(`.venv/bin/python` when running from backend). Black used the requested
`~/.local/bin/black` with the same credential isolation and timeout.

```text
cd backend
.venv/bin/python -m pytest tests/unit/test_daily_memory_sweep.py tests/unit/test_daily_memory_sweep_job.py tests/unit/test_daily_memory_sweep_inventory.py tests/unit/test_daily_sweep_summary_agent.py tests/unit/test_jit_qa_sweep_repair.py tests/unit/test_jit_qa_sweep_operator.py tests/unit/test_strict_firestore_transaction.py -q --disable-warnings
310 passed in 17.33s
.venv/bin/python -m pyright -p pyrightconfig.json --pythonpath .venv/bin/python
0 errors, 5988 warnings, 0 informations

# repository root
backend/.venv/bin/python backend/scripts/check_workflow_contracts.py
Workflow contract checks passed.
~/.local/bin/black --line-length 120 --skip-string-normalization --check <all 13 changed Python files>
13 files would be left unchanged.
FIRESTORE_EMULATOR_HOST=127.0.0.1:8789 GOOGLE_CLOUD_PROJECT=demo-daily-memory-sweep GCLOUD_PROJECT=demo-daily-memory-sweep MEMORY_ENABLED=on backend/.venv/bin/python backend/scripts/daily_memory_sweep_emulator_test.py
PASS: daily memory sweep Firestore emulator retry/interruption proof
(crash/deletion/generation/paid-wipe/pre-dispatch-release-contention/source-digest-binding/legacy-fence/source-projection/accounting-pagination/lost-accounting-refusal/window-admission/pre-lock-preflight/attested-skip/lock-projection)
```

The admission/skip proof helper is now explicitly called by the emulator runner;
its previous presence in the file and printed PASS labels were not evidence of
execution. The emulator was stopped after the proof. New hermetic tests exercise
locking during prompt preparation before both provider phases, permanent-state
reasons (including missing payload and changed digest), and truthful abandonment
receipts. Existing concurrency, mutation, onboarding and certified-release tests
continue to pass. The assertion's existing exact identity/claim/lease/margin/
single-use checks remain in the shared repair machinery.

No live payment, provider model, Omi service, cloud index or deployment was
exercised. No deployment observation was independently repeated. Setup's network
refresh, shared-hook rewrite and venv synchronization were omitted under the
worktree/execute-only/no-network constraints; the existing hook was verified.
Only a local commit is authorized; no push or PR is performed.
