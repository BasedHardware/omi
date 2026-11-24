# Conversation relevance terminal-path audit (2026-10-15)

Contract: a terminal row published in the default conversation list has a
well-formed relevance record identifying its verdict, deciding tier, bounded
reason, and authorized trigger. A finalization job state is not a relevance
verdict. `finalization_status` is optional for writers without a durable job.

This is a source/fixture audit, not a production account repair. The supplied
`ed296267-e37a-492c-9ce4-1abbb59c7f87` snapshot is the incident fixture;
no production documents were read or rewritten. A completed historical row
will not repair itself merely because this code is installed. No Jev/nano
threshold, recovery feature flag, client, or deletion contract changes.

## Complete writer surface

| Path / owning implementation | Terminal states | Decision before change? | Result / protection |
| --- | --- | --- | --- |
| Live listen / capture-end finalizer (`finalizer.py`, `process_conversation.py`) | Completed keep/discard; deferred processing; retry; dead-letter | Normal assessment yes; finalization failure no | Normal rules → Jev/nano → deterministic chain unchanged. Dead-letter now calls shared terminal decision before its atomic job/row write. |
| Client finalize and lost-dispatch relaunch (`lifecycle.py`, finalization outbox) | Same completed/deferred/retry/dead-letter states | Successful assessment yes; failure terminal no | Existing `CLIENT_FINALIZE` assessment still runs. Outbox generations fence duplicate/lost dispatches; orphan/dead-letter exits below now supply decisions. No client changes. |
| Direct server/developer/from-segments create (`create_completed_conversation`, `persist_processed_conversation`) | Completed; temporary processing; failed | Transcript path yes; bypass/early-return gaps possible | Lifecycle completion boundary fills absent/invalid records with named `lifecycle_terminal_default` policy, preserving existing valid verdicts. |
| External text/audio/message/workflow create (`_get_structured`) | Completed keep; processing failure | No: returned before relevance observer | Explicit `external_text_default` keep policy is observed and persisted. Existing integration enrichment behavior retained. Lifecycle boundary also covers exception/minimum returns. |
| Desktop JIT / free-tier / custom-STT deterministic minimum | Deferred processing or completed keep/discard; failed first-open returns completed+deferred | Initial normal/rules-only decisions yes; legacy first-open failure no | Existing `rules_only_relevance` remains. Retry re-arm transaction now stores `deferred_retry_default` when no valid decision exists. Nonpersisting budget exits do not independently publish rows. |
| Server recovery, flag off | Completed keep or typed failure → retry/dead-letter | Yes: `policy/server_recovery` on successful structuring | Intentional safety KEEP in `PROCESSING_MODES`, unchanged. New terminal default closes the typed-failure gap. `server_recovery` now has its own metric trigger instead of `other`. |
| Server recovery, minimum-terminal flag on | Original content-free rule discard; enriched keep; minimum failure → dead-letter | Successful keep/discard yes; failure terminal no | Existing feature-gated rules-only admission and protected-content CAS unchanged; dead-letter fills missing verdict. No broad recovery reassessment or threshold adjustment. |
| Ordinary stale processing orphan (`_complete_orphan_conversation_txn`) | Completed; ownership divergence refuses | No | Snapshot-bound rules, calendar/photo protections, or `orphan_terminal_default`. Same admission generation fence. |
| Legacy unstampable orphan | Completed if metadata fits; failed if mandatory decision cannot fit | No: status-only completion | Shared terminal path with `oversized_terminal` provenance. Captured content is never trimmed. |
| Oversized in-progress capture (`oversized_conversation_terminal.py`) | Completed if decision fits; failed otherwise; owned/recent/below-ceiling rows refused | No: status-only completion | Mandatory decision survives optional-title size guard. If mandatory metadata exceeds the actual 1 MiB ceiling, status becomes failed, outside default processing/completed lists. |
| Abandoned BYOK (`_abandon_byok_finalization_job_txn`) | Job dead-letter; bound row completed, or failed at ceiling; generation divergence fenced | No | `byok_abandoned` rule/policy decision in the same transaction; preserves BYOK ownership and no-integration-fanout behavior. |
| Immutable Limitless / transcript-file imports (`persist_imported_conversation`) | Create completed once; duplicate import no-op | No | Explicit `import_default` keep policy: deliberate user import remains kept. Create-if-absent still preserves user edits. |
| Sync intake and subsequent append (`utils/sync/assignment.py`) | Completed rule discard or provisional keep; live target retains lifecycle; donor redirects hidden | Discard yes; keep/promotion could clear decision to None | Existing intake discard rules unchanged. Every keep/promotion now records `sync_intake_default` if no valid keep exists, before the transactional survivor write. Paid `SYNC_UPDATE` assessment follows over full transcript. |
| Sync processing (`utils/sync/pipeline.py`) | Completed keep/discard or recovery terminal | Normal assessment yes | Lifecycle result boundary now supplies a decision if any minimum/bypass omits one; transcript-revision CAS still rejects stale processors. |
| Explicit merge (`merge_conversations.py`) | New survivor processing → completed; source rollback to completed; donors hidden/deleted | Survivor yes (`policy/merge`); legacy source rollback not guaranteed | CAS completion transitions and durable merge-job crash rollback (`database/conversation_merge_jobs.py`) now fill missing decisions. Any valid prior keep or discard survives, even when the legacy discarded flag disagrees. Only an explicit user restore replaces a discard. |
| Smart merge survivor / refresh | Existing survivor completed; refresh processing → completed; donors hidden | Normal survivor decision / `policy/smart_merge` yes | Existing relevance policy and refresh lease/revision fences remain. Generic completion boundary covers absent records. Donor tombstones are untouched. |
| User discard / restore / deletion | Discard stays hidden; restore makes explicit user keep; deletion never recreated | Existing user-owned contract | Restore now adds user-decision metadata after the unchanged tombstone fence. No deletion/discard semantics change. New helper never turns an existing discard into keep, respects restores, and normal persistence still refuses missing/deleted rows. |
| Approved historical noise close/restore (`database/stuck_backfill.py`) | Completed+discarded close; revision-fenced restore to saved in-progress state | No; never a visible terminal | Existing atomic discard + no-derived-effects + plan marker keep it hidden. Tripwire exempts only that full payload; no backfill is executed by this audit. Silent-summary processing keeps its existing explicit policy verdict. |
| Finalization job completion/fanout bookkeeping, audio/segment/photo metadata updates | Do not independently create or terminalize a conversation row | Not a separate decision path | Job completion requires committed fanout; conversation completion is owned by processing. Metadata writes cannot set lifecycle fields through generic update. |
| Canary and fixed local/offline fixture creation | Completed | Caller-dependent; fixture batch had no decision | Dream canaries use guarded lifecycle creation. Chat-first E2E batch seeding now stores explicit `fixture_seed_default` policy; existing runtime/account guards still prohibit production fixture writes. |

## Shared terminal decision

`utils/conversations/terminal_relevance.py` validates existing records, preserves
valid prior decisions and rule KEEP outcomes, and supplies a total decision.
Malformed prior keep records are repaired conservatively without reversing their
positive evidence, including rule and calendar keeps. Repair retains a recognized
prior trigger, since `server_recovery` provenance also fences capture-byte
preservation during persistence.
Terminal recovery strictly decodes the held transcript snapshot before using
`deterministic_relevance`. Ambiguous/substantive text stays kept with a bounded,
path-specific policy reason; reminders and substantial-length rules retain their
rule provenance. Non-audio/import sources, user curation, photos, and wake-word evidence bypass transcript
rule discards. A legacy child photo also protects even without a parent flag.

Only a rule-level discard attempts calendar reads. Stored/direct calendar intent
and accepted Google Calendar overlap protect it. Unknown windows or read/provider
failures keep conservatively; they are not recorded as proven calendar overlaps.
For dead-letter, provider evidence is resolved before entering the Firestore
transaction, using the existing calendar helper with a ten-second async timeout
and no new auth-refresh behavior. Errors/timeouts become uncertain evidence and
still allow an atomic completed keep. Negative evidence is reused only for the
same recording window; current inline calendar intent still protects the row.
All photo transaction reads occur before writes. No paid relevance model runs in
these failure terminals. Existing provider/normal relevance thresholds are unchanged.

The mandatory decision is part of the base terminal update, while title and retry
markers remain optional under the size guard. The former status-only overflow
escape is removed. A truly full document receives only `status=failed`, which
shrinks the original processing/in-progress state and is excluded both by the default
list's status filter and by the shared `is_visible_conversation` predicate, including
status-unfiltered readers and readers requesting discarded rows. This is a deliberate deviation from the former keep-at-all-
costs terminal behavior, necessary to avoid a visible undecided row without
removing captured data. It does not set discarded or deleted.

New outcomes use `omi_conversation_relevance_decision_total` with distinct trigger,
verdict, deciding tier, and closed terminal reason labels imported by `utils/metrics.py` from
`utils/conversation_relevance_labels.py`.
Recovery degradation and size exhaustion also use the shared fallback emitter.
Terminal discards and document-ceiling failures invalidate people-stats and refresh search after successful transaction return; aborted attempts publish no observer effects.
Counters emitted in transactions count attempts, so contention retries can repeat
an increment; these are not exactly-once row counts.

## Proof and limits

- `test_terminal_relevance.py`: incident snapshot (contentless, reminder, ambiguous),
  every declared terminal path, malformed decisions, calendar errors/overlap,
  existing rule keeps, restored/discarded rows, photos, wake words, unreadable
  transcripts, distinct metric labels, unchanged server-recovery policy.
- `test_dead_letter_visible_row_title.py`: real atomic dead-letter writer,
  legacy undescribed child photos, calendar override, rule discard, title/retry
  behavior, mandatory decision near the ceiling, nonvisible failure at the ceiling.
- `test_conversation_finalization_jobs.py`, `test_byok_abandonment_reconciliation.py`,
  `test_oversized_in_progress_close.py`: leases/generation fences and actual terminal writes.
- `test_conversation_lifecycle_contract.py`: real lifecycle creation/import and
  existing missing/deleted-row persistence fences; `test_sync_cross_job_assignment.py`:
  real intake survivor promotion records a keep. `test_recovery_discard_pipeline.py`
  exercises encoded capture preservation, corruption, restores and raced edits
  through the real recovery/dead-letter writers with explicit terminal decisions.
- `test_chat_first_e2e_fixture.py`: fixed local/offline identities cannot be selected in production, and actual fixture seeding stores its explicit keep decision.
- The full relevance, finalization, and selected sync/lifecycle suites exercise the
  normal decisions alongside these fallback paths. Test results belong in the
  session report; no deployment or production repair is implied.

A historical `completed` row without `finalization_status` cannot identify its
writer by shape alone: immutable import, sync intake, direct processing, merge
rollback, and orphan completion all legitimately have no durable job status.
This audit traces those writers, but does not attribute the supplied 08:27Z account
example to one writer without live provenance. The borderline Jev keep at 0.78
against 0.8 remains unchanged.


## Round 2 review corrections

The completion primitive now preserves any valid verdict regardless of the stored
`discarded` flag. Explicit `sync_relevance_user_kept` or `user_restore` is required
to replace a prior discard. Both lifecycle transition and completion entrypoint tests
seed legacy `filler_only` / `empty_transcript` decisions with `discarded=false`
and assert the verdict survives and the shared reader continues to hide the row.

The total-decision tests pin assessment by terminal path and inventory production
call sites; policy stamps cannot silently enable transcript assessment. The
existing lifecycle tripwire now rejects a literal completed conversation update
in an allowlisted storage file unless that same payload has `relevance_decision`.
Variable payloads retain behavioral contract coverage rather than claiming full
static data-flow analysis. Job-only completion writes remain separate.

Calendar provider calls are outside the dead-letter transaction. The public
wrapper test injects a provider timeout, asserts probe-before-transaction order,
and verifies status, flag, and keep decision in the same conversation write.
The size-ceiling choice is reader exclusion for `status=failed`, including
status-unfiltered readers; content and tombstones remain untouched.

Round 2 targeted verification covered 31 unit files (1,303 cases), including all
relevance suites and terminal/dead-letter, lifecycle, sync visibility, recovery,
and fixture contracts. Failing fixture expectations were corrected and their
files rerun successfully. Backend `test-preflight.sh` passed 17 checks with nine
optional environment/service warnings. The async-blocker scan and lifecycle
write guard passed. No live provider or deployed-product acceptance is claimed.


## Wave-2 integration (2026-10-23)

Rebased onto main `53c38ccd984cb50e15d13e6fd33f115bf646bf5d`. The
`conversation_terminal_title.dead_letter_conversation_updates` payload composes
the mandatory relevance record with main's deterministic title and conditional
`summary_retryable` marker; `_mark_finalization_dead_letter_txn` writes that
payload once, atomically with the job terminal and processing-attention item.
Attention's reads and all photo probes remain before the first transaction write.
The transient transcript fixture asserts the decision, deterministic title and
retry flag coexist in the same conversation update. Near the document ceiling,
only title/retry metadata may be omitted; the decision remains mandatory.

Main's lifecycle transitions require an expected status and retain CAS, privacy,
and explicit discarded-source merge guards. The retired unconditional status
writer and old free-tier terminal payload are not restored. Durable merge crash
rollback stamps its exact bound source snapshot, preserves legacy rule discards
even with `discarded=false`, and leaves a newer merge binding untouched. Main's
`silent_backfill` processing trigger is recognized as existing decision provenance
without changing its policy, classifier, approval fences, or delivery behavior.

The existing eight-word deferred placeholder builder now lives beside the other
pure title helpers in `deterministic_minimum.py`, keeping the processing
coordinator below main's file-size ratchet without changing title policy.

## Round 5 flags-off parity diagnosis (2026-10-23)

Verdict: **A, intended mandatory stamp**, for every failing parameter. A local
payload-dump patch reproduced 18 failures / 22 passes at head `00b5510582d`.
Each complete JSON pair was recursively compared: the only two changed locations
were the returned survivor (or finish-hook survivor) and its persisted row, both
adding exactly the same `relevance_decision`. All other payload bytes, including
logs, routing, transcript segments, revisions, and flags, were unchanged. The
dump patch was removed before validation.

At the reported index 3090, the old bytes contain
`"private_cloud_sync_enabled":false,"source":"omi"`; the new bytes contain
`"private_cloud_sync_enabled":false,"relevance_decision":{...},"source":"omi"`.
The added record is exactly:

```json
{"decided_by": "policy", "reason": "sync_intake_default", "rules_version": 1, "trigger": "sync_intake", "verdict": "keep"}
```

The harness generates bytes from frozen source in
`tests/unit/fixtures/sync_lineage_main_parity.json`; there is no regeneration
script or separate expected-byte blob. The fixture retains the original lineage
baseline revision and now records one explicit expectation update (including its
original source hash): a literal keep record on a previously undecided sync
survivor. The assignment source hash is recomputed. The literal does not call the
serving stamp helper, and the complete byte-equality assertions remain unchanged.
Resolver and process-segment frozen sources are unchanged. No serving code or
feature gating was changed; intake provenance is mandatory across cohorts.

Parameter IDs below are the exact original pytest IDs. `assignment` expands to
`test_assignment_matches_frozen_main_or_unstamped_gap_routing`; `process` expands
to `test_process_segment_saved_rows_results_finish_and_log_bytes_match_main`;
`excluded` expands to `test_excluded_cohort_stays_main_even_with_both_flags_on`.

| Test | Parameter | First byte diff | Verdict | Changed locations |
| --- | --- | --- | --- | --- |
| assignment | `disabled-typo-all_repeat` | 2292 | Intended stamp only | result survivor + persisted survivor |
| assignment | `disabled-typo-mixed1200` | 3062 | Intended stamp only | result survivor + persisted survivor |
| assignment | `disabled-typo-mixed40` | 3090 | Intended stamp only | result survivor + persisted survivor |
| assignment | `disabled-typo-new_row` | 3062 | Intended stamp only | result survivor + persisted survivor |
| assignment | `disabled-typo-pinned` | 1259 | Intended stamp only | result survivor + persisted survivor |
| assignment | `disabled-typo-same_range` | 696 | Intended stamp only | result survivor + persisted survivor |
| assignment | `off-all_repeat` | 2292 | Intended stamp only | result survivor + persisted survivor |
| assignment | `off-mixed1200` | 3062 | Intended stamp only | result survivor + persisted survivor |
| assignment | `off-mixed40` | 3090 | Intended stamp only | result survivor + persisted survivor |
| assignment | `off-new_row` | 3062 | Intended stamp only | result survivor + persisted survivor |
| assignment | `off-pinned` | 1259 | Intended stamp only | result survivor + persisted survivor |
| assignment | `off-same_range` | 696 | Intended stamp only | result survivor + persisted survivor |
| excluded | `disabled-typo` | 3090 | Intended stamp only | result survivor + persisted survivor |
| excluded | `off` | 3090 | Intended stamp only | result survivor + persisted survivor |
| process | `disabled-typo-texts0-True` | 1253 | Intended stamp only | finish survivor + persisted survivor |
| process | `disabled-typo-texts1-True` | 2313 | Intended stamp only | finish survivor + persisted survivor |
| process | `off-texts0-True` | 1253 | Intended stamp only | finish survivor + persisted survivor |
| process | `off-texts1-True` | 2313 | Intended stamp only | finish survivor + persisted survivor |

Calendar overlap, rule keeps, photos/wake words, user discards and tombstones
retain their existing protections. No thresholds, lexicon, backfill, client, or
production data were changed. Raw synthetic payloads and per-file logs remain
local at `/Volumes/Ephemeral/scratch/discard-round5/`.

Round 5 verification: 49 unit files each ran in a separate pytest process with
`backend/.venv/bin/python -m pytest <file> -q --tb=short`: **1,949 passed**, no
skips or failures. This includes all 40 flags-off parity cases and the relevance,
terminal/dead-letter, finalization, lifecycle, client-processing and lineage
suites. The lifecycle write guard and `make preflight` (37 local checks) passed.
The standalone backend preflight uses `PYTHON=.venv/bin/python`; the initial
system-Python invocation was corrected. Missing local pinned test dependencies
(`fakeredis==2.36.2`, `fake-firestore==0.13.1`) were installed before resuming the
extra assignment-recovery suite. The pre-existing uncommitted
`testing/import_isolation.py` change was preserved and present during testing;
it is outside this Round 5 commit.

Current-PR metadata validation separately fails its synthetic-merge line-count
check: `origin/main` at `fef4dd8fd8181f1e7c45eab223f22987ecd85530` conflicts with
the original `00b5510582d` head in `tests/fast_unit_duration_allowlist.txt`.
A read-only `git merge-tree --write-tree origin/main 00b5510582d` reproduces the
same conflict without any Round 5 edits. Local preflight success is not current
main merge readiness. No rebase, push, merge, deployment, or GCP tier was used.
