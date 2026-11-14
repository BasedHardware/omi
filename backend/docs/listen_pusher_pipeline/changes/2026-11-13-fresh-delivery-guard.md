Fresh-first step 1 adds metadata and measurement only. It changes no admission,
merge ordering, predecessor fence, projection, enrichment routing or release policy.

`results.fresh_capture` is written only by `OrderedMerge.commit_next` in the
transaction that commits the result log row. It copies `job.fresh_capture is True`;
missing stamps and every other value become `False`. Existing results are not
backfilled. Erasure may discard the field with the rest of the row's metadata.
The only semantic reader introduced here is
`database.batch_pipeline_fresh_guard.fresh_committed_counts`.

Reader audit before implementation (origin/main; #25210 still open): searched
all Python under backend for literal `results` store/ref/get calls, computed
`*_results` collections, result iteration, and `fresh_capture` consumers, then
followed the generic store adapters. Consumers select named fields; none uses
an unknown field or result-level `fresh_capture` as a decision signal.

| Readers / adapters | Existing interpretation; service scope |
| --- | --- |
| `utils/batch_pipeline/{merge,scheduler,provider_stt}.py`; `database/batch_pipeline_{coalescing,paid_attempt,recognizer_receipts,terminal_empty,artifact_missing,speech_redrive}.py`; `database/{batch_final_pass,batch_voice_evidence}.py` | Result existence, sequence or explicit receipt/artifact fields; backend-integration, sync handlers and GKE batch-worker/diarizer runtime import these shared modules. Job-level class reads remain job reads. |
| `utils/batch_pipeline/{projection,projection_drain,projection_discovery,projection_followup,projection_repair,voice_evidence}.py`; `database/batch_pipeline_{projection,projection_session,projection_privacy,projection_release,privacy}.py` | Projection state, binding, predecessor, privacy and named receipts; serving/backend-integration. Discovery uses store queries; extra metadata is ignored. |
| `utils/batch_pipeline/{retention,held_dead_letter,held_coverage}.py`; `database/batch_pipeline_{store,purge,conversation_purge,quarantine_recovery}.py` | Cleanup, recovery and metadata stock/age queries use named fields; shared serving/worker paths. Erasure selects its retained metadata explicitly. |
| `utils/batch_pipeline/{enrichment,metrics}.py`, `database/outbox*` | Enrichment consumes its outbox/job priority and projection receipt, not this result field; existing metrics select receipt/state/age fields. |
| `database/jobstore/{dual_store,postgres_store,codec,backfill}.py`; `database/batch_pipeline_shadow_hook.py` | Generic document copy/encoding and parity may carry or compare the new field. Typed Postgres queries select explicit existing fields; no ordering or routing decision uses it. DualStore delegates count client/namespace to its Firestore primary. |
| `testing/pipeline_sim/{store,postgres_store,sim,trace,scorer,policy_invariants}.py`; `testing/{batch_replay,store_fixtures,sync_cloud_tasks_stack}`; unit MemoryStore | Dict/document adapters preserve arbitrary fields; assertions and traces select named fields. Transition traces select named fields; final-result snapshots contain the full row, so goldens are regenerated with only the added fresh_capture boolean. |
| `scripts/{batch_pipeline_held_disposition,batch_pipeline_terminal_empty,batch_pipeline_artifact_missing,batch_pipeline_speech_redrive,reconcile_batch_projection_ghost_holds,redrive_staging_inputs}.py`; replay/owner-lab metadata tools | Operator and test readers inspect named custody/projection fields; no unknown-field routing. Artifact paths named `results` are encrypted blobs, a separate namespace from result-row metadata. |

These are source-version compatibility claims for the checked-out main and the
new PR. Older deployed revisions using these readers ignore the added field;
the release owner must record image SHAs for both merge writers before live
verification. This audit does not claim to have inspected unrecorded images.

The serving maintenance leader samples two Firestore counts at most once per
60 seconds over `fresh_capture == True` and the inclusive commit interval
[now−1200, now−600] seconds. The second count adds `projection_state == pending`.
Gauges: `omi_batch_pipeline_fresh_committed_window_total`,
`omi_batch_pipeline_fresh_unprojected_window_total`,
`omi_batch_pipeline_fresh_unprojected_ratio`,
`omi_batch_pipeline_fresh_guard_sample_age_seconds`. An empty cohort has no
ratio. Either failed query removes both counts and the ratio; age continues
from the last successful pair (absent until the first success). At 120 seconds
counts and ratio expire even if supervision stops. Leadership loss hides the
sample. The existing advisory maintenance lease's fail-open behavior is
unchanged; this measurement is not an authorization gate.

`BATCH_PIPELINE_FRESH_GUARD_ENABLED=off` (also false/0/no) suppresses queries and
all four gauges, including at scrape time. It is on by default and read through
the registered policy kill-switch helper, with a helper-backed flag-budget entry.
The reviewed lifecycle writer inventory includes `fresh_capture` in the merge
transaction payload. The unconditional
row field rolls back by revert only; stamped rows have no other semantic reader.

Read cost per sample: two count RPCs, about one billed document read per 1,000
index entries per count (minimum one each): approximately
max(1, ceil(total/1000)) + max(1, ceil(pending/1000)) reads, normally two per
minute / 2,880 per day per active maintenance leader. The extra leader check
also reads the existing lease metadata once per maintenance call (including
calls where sampling is not due); no additional lease document is introduced. No documents, transcripts
or audio are streamed. Both shapes have generated prod/dev composite indexes.

Release acceptance remains on SCA-2012: after the release owner deploys indexes
and code to backend-integration AND the GKE batch worker, compare the guard to
the ro-prod projection_cohort.py hand counts on two windows at least 30 minutes
apart (within 1 percentage point), and observe sample age under 120 s for an
hour. No deployment, activation or production reads were performed by this PR.
