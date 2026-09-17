# Sweep admission, rollout and paid-unlock replay

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
`invocation_pending` / `invocation_indeterminate` reasons. An existing pre-lock
fence found by the bounded historical lookup reports
`historical_invocation_unresolved`. These are allowlisted content-free tokens.
Onboarding now uses stable source/window/generation ownership and a separate
input digest too, closing its returned-output/stage-gap transcript-edit defect.
An account/source generation change admits a legitimately different invocation;
stale workers cannot finalize or apply it under the new generation.

## One operator exit, using existing repair attestation

The existing repair function and QA repair CLI also accept:

`ATTEST_SKIP_WINDOW_WITHOUT_DISPATCH_AND_WORKER_TERMINATED`

Use it as `--attestation-confirmation`, together with the existing
`--authority` and `--attestation-reference` arguments. It records
`operator_attested_skip_window` through the same receipt schema, identity,
claim ID, claim timestamp, operator identity and evidence-reference validator
as `operator_attested_no_dispatch`. The assertion explicitly accepts losing
this window's output and asserts that its worker has terminated; it does NOT
assert that the prior provider never ran. The lease plus the existing two-minute
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

## Locked content and atomic paid unlock

Locked rows are excluded before provider input, and counted in
`locked_rows_excluded` without IDs or content. The day can complete, including
complete-zero, so free users progress. All three payment paths already call
`unlock_all_conversations`; their sibling memory/action-item unlocks do not
own conversation source identity and do not separately rotate it.

Conversation unlock now processes batches of at most 100 references. Each
transaction reads deletion, canonical control, cursor, prior replay handoff,
user timezone and current locked rows before any writes. It atomically:

1. Unlocks only rows still locked.
2. Bumps canonical source generation, invalidating old canonical writers.
3. Rewinds the cursor to the day before the earliest unlocked local start date,
   preserving any earlier pending work and advancing the cursor CAS generation.
4. Writes `memory_control/daily_memory_sweep_unlock`, containing only owner,
   generations, earliest replay date, previous completed-date high-water mark
   and timestamp.

Without a cursor timezone, the transaction reads the user's persisted
`time_zone` (UTC if absent). No separate post-unlock bump can be lost in a crash.
A retry with no locked rows does nothing. Later batches merge the earliest date
and high-water mark, and atomically invalidate work from earlier batches.
Missing/string-typed start times retain the pre-existing timestamp-query
limitation: those rows unlock, but cannot themselves supply a replay date.

The existing scheduler drains at most 3 days per user per run (1 in QA), with
at most 32 candidates and 16 canonical writes per day, across at most 400 UIDs.
Total replay spans the finite range from the earliest unlocked day through the
current completed day; a long history may take many runs. The unlock call does
not invoke models or synchronously backfill those days. The unlock transaction
has at most 105 document reads and 103 writes. The existing payment unlock scan
still visits all locked rows; only each transaction and each sweep run are
bounded, not the total payment scan or number of future runs.

Old cached summaries and prebuilt packets are never restamped. The exact
handoff authorizes bypass of an older source generation's artifacts from that
account starting at the replay date, including an already-produced pending day.
Current-generation artifacts retain their usual validation. New stages are
stored in the existing generation-scoped namespace, with `unlock_replay` and
`supersedes_source_generations_before` ancestry. Prior stages remain historical
records until normal retention; prior UI daily-summary documents are retained
and no duplicate UI summary is created. This sweep still owns memory extraction,
not regeneration of the user-facing daily-summary text.

Historical replay candidates use generation-scoped provenance. Exact-subject
or occupied-slot facts are explicitly recorded as skipped; replay can add facts
with no existing occupant. It does not supersede an occupied slot, even if the
unlocked material suggests a correction. This conservative limit avoids
rewinding newer/user-authored knowledge and avoids duplicating existing facts.
**Not implemented:** automatically adjudicating conflicting historical facts
or regenerating prior UI summaries. Those need a separate recency/provenance
policy and the daily-summary owner's update contract; neither is silently
approximated here. Later forward days retain ordinary slot-refresh behavior.

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
page or a later insert is not rechecked. Even selected rows can change after
reading. There is **no explicit settle margin**: yesterday becomes eligible at
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

## Local verification (2026-09-18)

All Python commands used the shared `backend/.venv/bin/python`,
`GOOGLE_APPLICATION_CREDENTIALS=/nonexistent/adc.json`,
`CLOUDSDK_CONFIG=/nonexistent`, and `timeout 900`. The venv was not modified.

```text
pytest: seven sweep/job/inventory/agent/repair/operator/strict-transaction unit files
291 passed in 6.68s
python -m pyright -p pyrightconfig.json --pythonpath .venv/bin/python
0 errors, 6014 warnings, 0 informations
python backend/scripts/check_workflow_contracts.py
Workflow contract checks passed.
black --line-length 120 --skip-string-normalization --check (9 changed Python files)
9 files would be left unchanged.
Firestore emulator (loopback only, demo-daily-memory-sweep, MEMORY_ENABLED=on)
PASS: crash/deletion/generation/paid-wipe/pre-dispatch-release-contention/
source-digest-binding/legacy-fence/source-projection/accounting-pagination/
lost-accounting-refusal/window-admission/pre-lock-preflight/unlock-replay/attested-skip
```

The new behavioral tests also cover identity computation after committed
admission, onboarding's stage gap, mostly-discarded scans, contentless omissions,
post-projection changes, real payment-helper batching, generation-scoped stage
succession, occupied-slot preservation, foreign-reference rejection, and multiple
historical claim attestations. The tuple-result workflow gate now explicitly
covers the sweep admission/repair boundary. The narrow Firestore fixture only
adds document references to its existing ID projections; real emulator queries
exercise that shape too.

No Omi service, live payment webhook, provider model, production index, or cloud
rollout was exercised. No deployment observation was independently repeated.
The setup refresh, shared-hook rewrite and venv synchronization steps were
omitted to honor the worktree/execute-only/no-force constraints; the existing
hook dispatcher and interpreter were verified. No push or PR was performed.
