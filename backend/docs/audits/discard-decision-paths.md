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
| Explicit merge (`merge_conversations.py`) | New survivor processing → completed; source rollback to completed; donors hidden/deleted | Survivor yes (`policy/merge`); legacy source rollback not guaranteed | The status storage primitive in `database/conversation_status_transitions.py` and CAS completion transitions now fill missing decisions. Existing merge policy keeps and valid rule keeps survive. |
| Smart merge survivor / refresh | Existing survivor completed; refresh processing → completed; donors hidden | Normal survivor decision / `policy/smart_merge` yes | Existing relevance policy and refresh lease/revision fences remain. Generic completion boundary covers absent records. Donor tombstones are untouched. |
| User discard / restore / deletion | Discard stays hidden; restore makes explicit user keep; deletion never recreated | Existing user-owned contract | Restore now adds user-decision metadata after the unchanged tombstone fence. No deletion/discard semantics change. New helper never turns an existing discard into keep, respects restores, and normal persistence still refuses missing/deleted rows. |
| Finalization job completion/fanout bookkeeping, audio/segment/photo metadata updates | Do not independently create or terminalize a conversation row | Not a separate decision path | Job completion requires committed fanout; conversation completion is owned by processing. Metadata writes cannot set lifecycle fields through generic update. |
| Canary and fixed local/offline fixture creation | Completed | Caller-dependent; fixture batch had no decision | Dream canaries use guarded lifecycle creation. Chat-first E2E batch seeding now stores explicit `fixture_seed_default` policy; existing runtime/account guards still prohibit production fixture writes. |

## Shared terminal decision

`utils/conversations/terminal_relevance.py` validates existing records, preserves
valid prior decisions and rule KEEP outcomes, and supplies a total decision.
Terminal recovery strictly decodes the held transcript snapshot before using
`deterministic_relevance`. Ambiguous/substantive text stays kept with a bounded,
path-specific policy reason; reminders and substantial-length rules retain their
rule provenance. Non-audio/import sources, user curation, photos, and wake-word evidence bypass transcript
rule discards. A legacy child photo also protects even without a parent flag.

Only a rule-level discard attempts calendar reads. Stored/direct calendar intent
and accepted Google Calendar overlap protect it. Unknown windows or read/provider
failures keep conservatively; they are not recorded as proven calendar overlaps.
All photo transaction reads occur before writes. No paid relevance model runs in
these failure terminals. Existing provider/normal relevance thresholds are unchanged.

The mandatory decision is part of the base terminal update, while title and retry
markers remain optional under the size guard. The former status-only overflow
escape is removed. A truly full document receives only `status=failed`, which
shrinks the original processing/in-progress state and is excluded by the default
list's status filter. This is a deliberate deviation from the former keep-at-all-
costs terminal behavior, necessary to avoid a visible undecided row without
removing captured data. It does not set discarded or deleted.

New outcomes use `omi_conversation_relevance_decision_total` with distinct trigger,
verdict, deciding tier, and closed terminal reason labels imported by `utils/metrics.py` from
`utils/conversation_relevance_labels.py`.
Recovery degradation and size exhaustion also use the shared fallback emitter.
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
  real intake survivor promotion records a keep.
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
