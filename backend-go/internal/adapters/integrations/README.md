# Created-conversation integrations

The adapter sends the finalized revision to marketplace app callbacks and the owner's
developer webhook. `integrationfanout.Service` runs from the calling finalization job.
The receiver sees the existing JSON projection, an escaped `uid` query parameter and
`X-Omi-Idempotency-Key`. Successful status headers acknowledge delivery immediately.

Receipts live at `users/{owner}/integration_delivery_receipts/{hash}`. The hash covers
conversation ID, revision and destination ID. Each receipt stores only a delivered flag.
The owner deletion marker is checked in the receipt lookup before each send and again in
the receipt transaction. The queue guard serializes a canonical job with its takeovers and
queue-level account erasure. Once the receiver accepts, the delivered receipt skips the
request on later attempts. If the response or receipt is lost after the receiver acts, the
retry depends on the receiver honoring the same idempotency key.

| Delivery rule | Test |
| --- | --- |
| Eligible destinations are deduplicated. Successful and terminally rejected receivers are skipped on retry. A new revision sends again with a fresh key. | `TestFanoutRetriesOnlyUnsettledReceiversAndIsRevisionScoped` |
| A receiving app's 4xx, including 429, ends that app's delivery while the rest of the fanout continues. A 5xx retries within the job budget. | `TestFanoutRetriesOnlyUnsettledReceiversAndIsRevisionScoped`, `TestFanoutDropsTransientDeliveryOnFinalAttempt` |
| The job finishes with a delivery-drop cause after a destination spends its retry budget. | `TestFanoutDropsTransientDeliveryOnFinalAttempt` |
| A locked or discarded conversation produces no callbacks. A deleting owner produces no callbacks or new receipts. | `TestFanoutSkipsLockedAndDiscardedConversationsAndHoldsDeletingOwner`, `TestReceiptPreservesAcceptanceAndRefusesDeletion` |
| The receiver gets the JSON payload, owner, optional app headers and stable fanout key. Redirects are terminal. | `TestSenderPreservesWireContractAndRefusesRedirect` |
| Slow receivers time out before acknowledgement. Once a 2xx arrives, the response body cannot cause redelivery. | `TestSenderTimesOutBeforeHeadersButAcceptsWithoutWaitingForBody` |
| A live guard is required. The production sender validates every resolved address and dials only validated addresses directly. | `TestSenderRefusesPrivateAddressesAndInvalidGuards` |
