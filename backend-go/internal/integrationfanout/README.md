# Finalization fanout ports

Wire the service with the integrations HTTP sender and Firestore receipts. Register its
`Causes()` on the finalization kind. Call `Deliver` after the canonical revision has claimed
fanout, and pass the persisted Python-compatible fanout key when one exists. An error goes
through `queue.FromError`. Successful delivery with a dropped destination can be reported
with `queue.DoneWith(CauseDropped)` after finalization is committed.

Resolve destination settings for the owner on each attempt. Supply the owner opt-in, the
created-conversation trigger and any operational disablement. Supply the already redacted
and serialized JSON for each destination, including workflow external-data suppression for
apps and speaker and folder enrichment for the developer webhook. When a plugin requires
delivery signing, pass the signed payload and headers in memory. An empty app ID is reserved
for the owner's developer webhook. The service assumes one canonical job per revision.

| Rule | Test |
| --- | --- |
| A destination needs an enabled owner setting, a created-conversation trigger, an active webhook and a URL. | `TestOnlyEnabledCreatedTargetsAreEligible` |
