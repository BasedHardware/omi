# Conversation finalization

This package adds the ordinary finalization worker and its admission boundary. The
Firestore outbox commits intent and binding together. The queue receives the immutable
revision after that commit. Enqueue is idempotent, so a caller or outbox reconciler can
dispatch an accepted intent again. Queue rows contain the revision and trigger. BYOK
credentials exist only in the live resume and the guarded provider request.

`unit.go` declares the kind and input format. `rules` holds pure decisions. `service.go`
runs each external step under a queue capability. The job closes after the durable
fanout commit. Exhaustion checks for that commit before granting a requeue or dead
lettering. The package tests use real PostgreSQL workers and synthetic collaborators.
The Firestore implementation and cross-adapter test are described in
[`finalizationdocs`](../adapters/finalizationdocs/README.md).

## Contract coverage in this draft

| Rule | Assertion and test |
| --- | --- |
| F01 | Trigger table and early dispatch refusal. `TestF01ProcessingTriggerPolicy`, `TestF01DispatchRefusalPrecedesAdmission` |
| F02 | Ordinary lifecycle eligibility, two concurrent admissions, a single revision and no payload in the SQL row. `TestF02NewRevisionRequiresEligibleLifecycle`, `TestF02ConcurrentAdmissionReusesOneIntent` |
| F03 | Admission decision over current recovery facts and owner backfill availability. `TestF03RecoveryRevalidatesCurrentFacts` |
| F04 | Gated work stays unclaimed until live resume, which forwards the live key. `TestF04BYOKWaitsForLiveSecret` |
| F05 | Exact ordinary task fields, positive integral generation and reserved prefixes. `TestF05OrdinaryTasksRequireAnOpaqueJobAndPositiveGeneration` |
| F08 | Audio-only completion reserves custody first. Closed empty custody fences. `TestF08AudioOnlyRequiresCustodyBeforeCompletion`, `TestF08ClosedEmptyArchiveFencesWithoutDerivedWork` |
| F09 | Reload after meeting evidence and retry stale persistence against newer input. `TestF09WaitReloadsTailAndApplyRefusesAChangedSnapshot` |
| F10 | Input and output integrity checks and stable paid operation on retry, using the draft notes schema. `TestF10NotesReuseRequiresEnabledMatchingInputAndIntactOutput`, `TestF10LostPaidResponseUsesOneOperation` |
| F11 | Discard at fanout claim stops derived writes and delivery. `TestF11DiscardBeforeFanoutFencesEveryDelivery` |
| F13 | Recording, terminal and lazy effects policy. `TestF13RecordingTerminalAndLazyEffects` |
| F14 | Stable revision key across a transient retry and final drop. `TestF14IntegrationRetriesWithRevisionKeyAndDropsOnFinalAttempt` |
| F15 | Recover committed fanout after the last attempt loses the response. `TestF15CommittedFanoutWinsAtExhaustion` |
| F16–F17 | One transient budget requeue, deterministic cap and transcript preservation through the dead-letter boundary. `TestF16TransientExhaustionGrantsOneBudgetRequeue`, `TestF17DeterministicFailureDoesNotRequeue` |
| F27 | Nonblank overview or section bodies establish summary presence. `TestF27OverviewOrSectionMakesASummary` |
| F32 | A missing conversation fences before paid work or integration delivery. `TestF32MissingConversationFencesBeforePaidWork` |
| F34 | Distinct enrichment-envelope parsing, including mixed envelope rejection. `TestF34EnrichmentIsASeparateEnvelope` |
| F35 | Reconcile staleness and budget-delay defaults. The durable sync wait and redrive tests are in the job-adapter README. `TestF35OrdinaryPolicyDefaults` |

Unlisted rules and the rest of the listed rules remain open. This includes the HTTP dispatch and replay protocols, quiet storage-proof and
size-limit handling, smart absorb and sealed merge cleanup, durable episode
attachment, and the production notes and derived-effect policies. The replay-oracle comparison
is pending.

## Wiring dependencies

- The Firestore job adapter implements ordinary admission, accepted-claim fencing,
  fanout and terminal transitions. The merged conversation adapter handles guarded
  transcript load and title/overview compare-and-apply. The emulator compatibility
  test composes both. Worker wiring still needs the conversation policy fields,
  sections and hash writes, as well as object-lake transcript custody.
- Workerd can opt into lane 3's keyed gateway and guarded completion recovery.
  The family supplies the original queue row's creation time and checks for a
  recoverable completion before repeating a paid notes step. Serving use needs
  the gateway protocol and retention policies active on every replica.
- Lane 5's event and target fields match this worker's inputs. Its delivery service
  accepts a queue run and acquires its own guards. It needs a guarded entry point
  to implement the family port directly. The contract also allows previously successful
  destinations to receive a retry and separates the created-webhook from ordinary
  integrations.
- The draft format uses its own queue schema version. Worker wiring and replay against
  the Python corpus are still required before rollout.

## Additional policy tests

| Rule | Assertion and test |
| --- | --- |
| F21 | Cache reuse binds the pair, revisions and gap. Shadow cannot absorb. `TestF21SmartMergeRequiresEvidenceAndShadowCannotAbsorb` |
| F24 | Recovery rolls back before seal and stops cleanup after five claims. `TestF24MergeRecoveryChangesAtTheIrreversibleBoundary` |
| F25 | Client close and server occasion, tail and idle gates. `TestF25OnlyRealOccasionBoundariesCloseTheEpisode` |
| F26 | Eligibility, sync memo and committed fanout surviving a failed bounded hook. `TestF26EpisodeEffectsSkipUntrustedAndUnchangedCaptures`, `TestF26EpisodeFailureCannotUndoCommittedFanout` |
| F27 | Server minimum versus protected, manual, historical or short output. `TestF27OnlyEligibleServerMinimumsKeepDebt` |
| F28 | The empty-output rearm rule allows only two newer content revisions. `TestF28OnlyTwoNewContentRevisionsRearmEmptyOutput` |
| F37 | Unplaced retained identity advances activity once. `TestF37UnplacedSpeechAdvancesActivityOnlyOnce` |
