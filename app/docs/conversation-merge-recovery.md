# Manual conversation merge completion

`POST /v1/conversations/merge` allocates a **new** target ID before background work
and returns it as optional `merged_conversation_id`. Both legacy admission and
the lifecycle job use that same ID. Released clients may ignore the additive
field; a new client talking to an older server falls back to a fresh list only
after every source point-read returns 404. A completed original is never the
merged result.

`ConversationMergeWatch` supplies bounded, serialized point reads when a push
is delayed or unavailable. Only 404 proves source absence; locks, authorization,
transport and decode failures remain unresolved. The target must be completed
and unlocked. Push and polling converge through `ConversationProvider`'s one
list/search/processing/cache commit. That commit fences in-flight pages and
searches and suppresses merged-away source IDs until the account session ends.

Pending source/target IDs are journaled by account and API origin. Reopening or
refreshing restores observation without submitting another merge. Expiry stops
the watch and refreshes once; a later resume/manual refresh can retry. Account
clear/disposal cancels observers, and late reads cannot mutate a new session.
No transcript or audio is journaled, deleted, retranscribed or uploaded here.

## Existing server safety and rollout

Main already propagates authoritative source-deletion errors on the
`merged_into` path (#21544). A failure cannot dispatch merge completion, and a
target is retained once source deletion has begun. Lifecycle jobs additionally
retry sealed cleanup against the same target, with lease/source-binding fences
and without rerunning transcription. This change preserves lifecycle rollout
modes; it does not silently enable them or promise automatic repair of legacy
partial failures.

Deploy the additive backend response before releasing the mobile client for the
full known-target path. Verify real deployment/store receipts separately from
merge/CI. Historical merged-plus-source records need an authorized account trace;
do not automatically delete ambiguous originals or repeat a merge to repair them.

## Implementation and verification checklist

- [x] Same target returned by both admissions and passed to their worker/job.
- [x] Typed source absence, new target readiness, bounded retries and scope fences.
- [x] Restart journal and cache/search/pagination reconciliation.
- [x] HTTP client/provider/production-row foreground and reopen journey with no push.
- [x] Source-delete refusal, sealed cleanup retry and rebound-source regressions.
- [ ] Required CI on the final pushed revision and final diff review.
- [ ] Backend deployment, Android/iOS store release and customer retest.

The hermetic journey substitutes auth, backend storage/worker effects and
SharedPreferences platform IO. Backend TestClient and coordinator tests cover
admission and failure semantics separately. This is local integration evidence,
not a production-account repair or physical Android notification test.
