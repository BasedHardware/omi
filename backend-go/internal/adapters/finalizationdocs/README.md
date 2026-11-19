# Finalization job documents

The finalization outbox creates or reattaches the deterministic job and binds the
conversation in one deletion-fenced Firestore transaction. It writes only
lifecycle fields on the conversation. After the commit, the family dispatches
the intent to PostgreSQL. An enqueue retry reuses the committed job.

This adapter owns the job and binding transaction. Processing-result patches and
Home receipts belong to the merged conversation adapter. This adapter currently
admits ordinary capture and explicit client end. Recovery and silent backfill
need the recording-session and content-custody checks before they can admit.
Legacy photo sidecars and object-lake transcript custody also need a reader.
Do not enable this adapter until the deployment grants one dispatcher ownership
of each intent.

| Rule | Emulator test |
| --- | --- |
| F02. Concurrent ordinary admission creates one job, one binding and one projection increment. | `TestF02ConcurrentFirestoreAdmissionCommitsSingleBindingAndProjection` |
| F02. An existing deterministic job keeps the original trigger and BYOK requirement. | `TestF02ReattachPreservesTheOriginalIntent` |
| F04. Failed SQL dispatch leaves the binding and job recoverable. | `TestF04DispatchFailureCanReplayCommittedFirestoreIntent` |
| F32. Deletion and cross-tenant guards prevent admission. | `TestF32DeletionBarrierAndWrongTenantMakeNoWrites` |
| F06. A live foreign lease is held, duplicate claims are free, and takeover fences old epochs. | `TestF06TakeoverAndForeignLeaseFenceOldEpochs`, `TestF06NewerDispatchGenerationRefusesTheEarlierQueueIntent` |
| F11. Deletion and discard refuse the fanout claim. | `TestF11DiscardOrAccountEraseRefusesFanout` |
| F15, F38. Fanout recovery takes precedence over dead letter. Racing terminal writes increment the success shard once. | `TestF15AndF38CommitWinsAndTerminalProjectionIsExactlyOnce`, `TestF38UnstampedLegacyTerminalDoesNotChangeTheProjection` |
| F17. Failure closes the still-bound processing row with its speech intact and writes one attention item. | `TestF17DeadLetterClosesBindingPreservesSpeechAndWritesAttention` |

The queue claim token maps to a separate Firestore wire lease epoch. Each write checks both. Begin admits generation one and successors reserved by the Go adapter. BYOK abandonment still needs an entry point. This adapter is not a
coexistence protocol for dispatching the same job from Python and Go. The
failure transaction covers ordinary inline speech. Terminal title selection,
document-limit fallback, and compressed/described-photo retry eligibility remain
open.

F35 records a generation and bounded sync wait before yielding the SQL attempt.
The next claim enforces the durable deadline, including after a crash before
the yield. Operator redrive prepares the still-bound Firestore job before
resetting SQL and retains the lifetime grant count.

| F35 behavior | Emulator test |
| --- | --- |
| Thirty-second boundary, three redispatches, old epoch and the 600-second cap | `TestF35SyncRevisionQuietBoundaryAndRedispatchLimit`, `TestF35SyncRevisionWaitRetiresAtAgeBound` |
| Manual counter reset preserves the grant, duplicate preparation and prior epoch are inert | `TestF35ManualRedrivePreservesGrantAndRejectsPriorEpoch` |

The compatibility test `TestF09MergedDocumentAdapterFencesNewerInputAndUpdatesHome`
runs a real PostgreSQL worker against these transactions and the merged
conversation reader and compare-and-apply patch on a Firestore emulator. The
gateway response and downstream effects are synthetic. Sections, hashes and
additional policy fields require a production processing port before wiring.
