# Created-conversation integrations

The adapter posts the finalized conversation to marketplace apps and the developer webhook.
Apps receive `X-Omi-Idempotency-Key` and the developer webhook receives `Idempotency-Key`.
See [the finalization ports](../../integrationfanout/README.md) for target resolution and
the outcome contract for webhook health, usage, app messages and developer DLQ.

Receipts live at `users/{owner}/integration_delivery_receipts/{hash}`. The hash covers
conversation ID, revision and destination ID. Each receipt stores only a delivered flag.
One guarded Firestore transaction looks up the batch and checks the deletion marker.
Each terminal result writes its receipt in a separate fenced transaction. After a
transient result that needs no receipt write, a marker-only transaction gates the next
send. An already settled batch uses one transaction. The queue guard serializes the
canonical job with its takeovers and queue-level account erasure.

The adapter treats a 2xx as acceptance even if the response body is unreadable. It skips the
request after a terminal receipt is committed. If the response or receipt is lost after the
receiver acts, the retry depends on the receiver honoring the same outbound key.

| Delivery rule | Test |
| --- | --- |
| Destinations are deduplicated. Settled receivers are skipped on retry. A Python app delivery and Go replay use the same persisted key for that revision. | `TestFanoutRetriesOnlyUnsettledReceiversAndIsRevisionScoped` |
| Apps retry 408, 425, 429 and 5xx. Developer webhooks retry redirects at the original destination, 408, 429 and 5xx. Other 4xx responses are terminal. Transient responses honor Retry-After. | `TestSenderClassifiesReceiverStatusAndHonorsRetryAfter`, `TestFanoutUsesRetryAfterFromReceiver` |
| A transient delivery gets a terminal dropped receipt on the job's final attempt. | `TestFanoutDropsTransientDeliveryOnFinalAttempt` |
| A deleting owner is held for a minute. The batch lookup, marker refresh and receipt transaction reject a deleting owner. | `TestFanoutSkipsLockedAndDiscardedConversationsAndHoldsDeletingOwner`, `TestFanoutReportsTransientAttemptAndRechecksDeletionBeforeNextSend`, `TestReceiptPreservesAcceptanceAndRefusesDeletion` |
| Apps and developer webhooks receive their respective headers. The app query preserves unrelated bytes. The developer query uses Python-style ordered re-encoding. Both strip fragments and preserve URL Basic Auth. Redirects are never followed. | `TestSenderPreservesWireContractAndRefusesRedirect`, `TestDeveloperWebhookKeepsBasicAuthAndUsesDeveloperKey` |
| A slow receiver times out before acknowledgement. A 2xx remains accepted when the bounded response read times out, cannot parse a message, or exceeds the body cap. | `TestSenderTimesOutBeforeHeadersButAcceptsWithoutWaitingForBody`, `TestSenderKeepsAcceptanceWhenAppMessageIsInvalidOrOversized` |
| The production sender requires a live guard, validates every resolved address and dials only validated addresses directly. | `TestSenderRefusesPrivateAddressesAndInvalidGuards` |
| Rejected store calls, receipt conflicts and owner mismatches use the deterministic attempt budget. Transient and unclassified store failures use the transient budget. | `TestReceiptErrorsUseDeterministicOrTransientBudget` |
