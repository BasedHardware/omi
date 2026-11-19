# Conversation finalization

This package adds the ordinary finalization worker and its admission boundary. The
Firestore outbox commits intent and binding together. The queue receives the immutable
revision after that commit. Enqueue is idempotent, so a caller or outbox reconciler can
dispatch an accepted intent again. Queue rows contain the revision and trigger. BYOK
credentials exist only in the live resume and the guarded provider request.

`unit.go` declares the kind and input format. `rules` holds pure decisions. `service.go`
runs each external step under a queue capability. The job closes after the durable
fanout commit. Exhaustion checks for that commit before granting a requeue or dead
lettering. The Postgres tests use real workers and synthetic in-package collaborators.

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
| F35 | Lease, BYOK inactivity, budget delay and deterministic cap values. `TestF35OrdinaryPolicyDefaults` |

Unlisted rules and the rest of the listed rules remain open. This includes the HTTP
dispatch and replay protocols, smart and explicit merge, quiet checks, episodes, summary
repair, and the production notes and derived-effect policies. The replay-oracle comparison
is pending.

## Wiring dependencies

- Lane 2 supplies guarded load and compare-and-apply for conversation fields. The outbox
  admission, fanout journal and terminal transitions need transactions spanning the
  conversation and finalization job. The current adapter does not expose those
  transactions or all fields used by the worker.
- Lane 3 accepts a correlated operation ID. It needs durable completion recovery and
  replay deduplication before it can implement this worker's paid port.
- Lane 5's event and target fields match this worker's inputs. Its delivery service
  accepts a queue run and acquires its own guards. It needs a guarded entry point
  to implement the family port directly. The contract also allows previously successful
  destinations to receive a retry and separates the created-webhook from ordinary
  integrations.
- The draft format uses its own queue schema version. Worker wiring and replay against
  the Python corpus are still required before rollout.
