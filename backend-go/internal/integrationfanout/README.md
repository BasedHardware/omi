# Finalization fanout ports

Wire the service with the integrations HTTP sender and Firestore receipts. Register
`Causes()` on the finalization kind. Call `Deliver` after the canonical revision has claimed
fanout. A persisted Python key must match `conversation:<cid>:finalization:<rev>` for this
conversation and is sent verbatim. With no persisted key, the service uses the canonical
job's operation ID. Revision numbers start at one.

Resolve destination settings on every claim. Supply the owner opt-in, created-conversation
trigger, operational disablement and whether the owner owns the app. Supply the redacted
JSON for each destination, including workflow external-data suppression for apps and speaker
and folder enrichment for the developer webhook. Pass signed payloads and headers in memory.
The empty app ID is reserved for the owner's developer webhook.

Consume `Report.Attempts` even when delivery requests a retry. Use each attempt's app ID,
HTTP status and failure class for circuit breaker and webhook health updates, including
auto-disable. Python skips app health updates for invalid target configuration and records
developer failures once delivery is terminal. `RecordUsage` identifies accepted marketplace
calls that should write `memory_created_external_integration`, and `Message` is the app's
optional response text for the conversation's app messages. `DeadLetter` identifies terminal
developer failures. Use the original target, failure details and the attempt's idempotency key
for the DLQ. The caller owns these effects and should dedupe them by revision, destination and,
for attempt-level effects, claim token. The report is in memory and settled receipts
suppress future reports for that delivery.

Use `queue.FromError` to handle a delivery error. After committing finalization, record
`queue.DoneWith(CauseDropped)` if delivery returned no error and `Report.Dropped` is true.

| Rule | Test |
| --- | --- |
| A destination needs an enabled owner setting, created-conversation trigger, active webhook and URL. | `TestOnlyEnabledCreatedTargetsAreEligible` |
| Only unsettled receivers retry. An exhausted destination is dropped and the job can finish. | `TestFanoutRetriesOnlyUnsettledReceiversAndIsRevisionScoped`, `TestFanoutDropsTransientDeliveryOnFinalAttempt` |
| Locked or discarded conversations are skipped. The Firestore fence pauses deleting owners and is rechecked between outbound calls. | `TestFanoutSkipsLockedAndDiscardedConversationsAndHoldsDeletingOwner`, `TestFanoutReportsTransientAttemptAndRechecksDeletionBeforeNextSend` |
| Attempt reports carry health data, marketplace usage eligibility, app messages and developer DLQ eligibility. The next claim respects an operational disablement. | `TestFanoutReportsAttemptsForHealthUsageMessagesAndDeveloperDLQ` |
| The persisted Python key is sent verbatim. A key for another revision and revision zero are invalid. | `TestFanoutRetriesOnlyUnsettledReceiversAndIsRevisionScoped`, `TestFanoutRejectsRevisionZero`, `TestDeliverRejectsMismatchedPersistedKey` |
