# Manual conversation merge completion

`POST /v1/conversations/merge` allocates a **new** target ID before background work
and returns it as optional `merged_conversation_id`. All manual merges use the existing durable lifecycle job, independently of the
broader capture/finalization canary. That job uses the same target ID. Released clients may ignore the additive
field; a new client talking to an older server falls back to a fresh list only
after every source point-read returns 404. A completed original is never the
merged result.

`ConversationMergeWatch` supplies bounded, serialized point reads when a push
is delayed or unavailable. Only 404 proves source absence; locks, authorization,
transport and decode failures remain unresolved. The target must be completed
and unlocked. Push and polling converge through `ConversationProvider`'s one
list/search/processing/cache commit. That commit fences in-flight pages and
searches and suppresses merged-away source IDs until the account session ends.

Cache read/modify/write transactions share one provider queue with page-cache
writes and old-server source cleanup. Each queued operation rechecks its account,
backend and generation before reading or committing. A merge retires its journal
entry only after its cache write completes, so simultaneous completions preserve
both targets across offline reopen. A failed transaction does not poison later
work, and a late completion cannot restore a target already incorporated by a
later merge. Target HTTP reads remain outside the persistence queue.
Cache pruning removes only authoritative merged-away IDs; unrelated rows pending
deletion remain available for Undo, including through the old-server fallback.

Pending source/target IDs are journaled by account and API origin. Reopening or
refreshing restores observation without submitting another merge. After the fast window, a source still marked merging remains observed at a
lower bounded rate for durable cleanup recovery. Final expiry refreshes once;
a later resume/manual refresh can retry the saved journal. Account
clear/disposal cancels observers, and late reads cannot mutate a new session.
No transcript or audio is journaled, deleted, retranscribed or uploaded here.

## Existing server safety and rollout

Main already propagates authoritative source-deletion errors on the
`merged_into` path (#21544). A failure cannot dispatch merge completion, and a
target is retained once source deletion has begun. Lifecycle jobs additionally
retry sealed cleanup against the same target, with lease/source-binding fences
and without rerunning transcription. Manual admission always uses this coordinator, so new merges cannot bypass
recovery through the default lifecycle shadow mode. Capture and transcription
rollout behavior is unchanged. A source carrying an earlier merge receipt is
refused at admission and worker reread, preventing a fresh merge from repeating
already-incorporated content after an older partial failure.

Deploy the additive backend response before releasing the mobile client for the
full known-target path. Verify real deployment/store receipts separately from
merge/CI. Historical merged-plus-source records need an authorized account trace;
do not automatically delete ambiguous originals or repeat a merge to repair them.

## Implementation and verification checklist

- [x] Atomic durable admission and the same target in off/shadow/serve lifecycle modes.
- [x] Typed source absence, new target readiness, bounded retries and scope fences.
- [x] Restart journal and cache/search/pagination reconciliation.
- [x] Concurrent completions, racing refresh, offline reopen, failed transaction retry and queued account/backend fences.
- [x] HTTP client/provider/production-row foreground and reopen journey with no push.
- [x] Source-delete refusal, delayed observation, sealed cleanup retry and rebound/consumed-source regressions.
- [x] Real Firestore emulator admission, lease expiry, correction transfer, partial failure and same-target recovery.
- [ ] Required CI on the final pushed revision and final diff review.
- [ ] Backend deployment and Android/iOS store release (release work).

Technical closure follows the verified fix on main. Support owns the separate
historical-account investigation and customer confirmation; neither is a code
readiness gate.

The hermetic journey substitutes auth, backend storage/worker effects and
SharedPreferences platform IO. Backend TestClient and coordinator tests cover
admission and failure semantics separately. This is local integration evidence,
not a production-account repair or physical Android notification test.
