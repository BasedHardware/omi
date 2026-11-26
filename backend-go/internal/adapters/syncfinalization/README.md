# Ordinary sync finalization adapters

The workerd runtime can bind these ports only with an explicit HTTPS origin, OIDC
audience and keyed notes gateway. The Python receiver also requires the workerd
service account and expected audience. This slice does not create Go intents.
A pre-existing job needs the ordinary sync trigger and the same Go owner epoch
on the job and conversation before the worker can enter its lifecycle.

| Port | Python reference | Proof |
| --- | --- | --- |
| Meeting evidence | `utils/conversations/meeting_evidence_admission.py`. Its wait applies to capture-end and client-finalize, while this adapter accepts only the sync trigger. | `TestReferenceBindsEveryCallToJobAndSyncRevision` |
| Notes and short clips | The serving one-shot prompt builder and short-clip policy run against the fenced snapshot. The Go gateway still owns the paid turn, and the Go compare-and-apply write records deterministic minimums and rule discards. Agentic, rich evidence and unresolved related-task inputs yield. | Paired ordinary-sync replay, including provider message digests |
| Batch custody | `utils/conversations/finalizer.py` and `database/conversation_finalization_jobs.py`. The ordinary sync worker refuses batch custody and cannot reserve, finish or delete batch recordings. | `TestSyncFinalizationHandlerRunsOnlySeededGoWork` |
| Effects | `utils/conversations/process_conversation.py` for preferred-app output, memory and task sources, and goal progress on a completed revision. The transcript checkpoint and app output commit with the effects receipt after rechecking the claim and source. Eager sync skips conversation vector refresh. Lazy effects require a separate Go debt owner. | `test_eager_effects_commit_only_current_outputs`, `test_lost_response_blocks_reexecution_across_takeover_and_append` |
| Integration targets | `utils/enrichment/callback.py` emits creation for a discarded-to-visible transition. Already-discarded inputs are outside Go serving scope. An older worker requesting targets receives an empty list under the usual claim fence. | `TestSyncFinalizationHandlerRunsOnlySeededGoWork`, `test_targets_respect_ordinary_sync_creation_policy` |
| Episode hook | `utils/episodes/member_notes.py::waits` and `utils/episodes/service.py::on_conversation_finalized`. Sync reconciliation must complete before terminal fanout. The claim-fenced receipt transaction also applies the canonical encrypted Home display. | `TestSyncFinalizationHandlerRunsOnlySeededGoWork` |

Mutating reference calls reserve a job-level receipt before starting and settle
it after the operation completes. An unresolved entry in
`go_sync_reference_operations` blocks replay and must block handback. It stays
unresolved across a worker takeover or an input revision change. The worker
yields while that result is unknown. There is no automatic reissue of the paid
Python effect on a missing response. Lane C must serialize its handback with
this receipt and the separate Go gateway and webhook reservations.

Keep the cohort closed. The ordinary-sync replay checks the active enrichment
callback and the workerd handler against the same stored inputs. Full relevance
and effects parity remain open, along with the read budget and drain gates.
