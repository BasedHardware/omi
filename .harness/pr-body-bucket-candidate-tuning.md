## Summary

- Reject generic workstream labels at the tagging acceptance gate with a deterministic stop-list (and all-tokens-generic compounds). `api` was accepted in dogfood because it appeared in the observations and had four supporting groups; that is the failure the two existing gates were meant to prevent. `omi` and other real project names still pass. `unknown` abstention is unchanged.
- Record director lane failures (`http_error`, quota cooldown, decode) as `decisionType = pending` with `lifecycleState = failed`. Provenance already carried the typed class; overwriting the decision as `silence` made 30 transport 502s in this session look like a choice to stay quiet. Lifecycle states are unchanged.
- Candidate firing: no code change. Investigation below.

## Candidate firing investigation (no change)

11 armed, 1 consumed, 4 expired unused, 6 still armed, over a 5-hour session.

- **12h expiry.** Same-session candidates cannot naturally expire in 5 hours. `decline()` collapses `expiresAt` to now (gate `show == false`, or grounding no longer valid), and `expireStale` then marks them `expired`. The 4 unused expiries are declines, which is the designed "answering false is common and correct" path. Lengthening or shortening 12h from this sample would be tuning to noise.
- **Workstream lookup.** Lookup is `bucketID` or `workstreamTag IN this bucket's tags`. 2 distinct tags (`omi` on 7 buckets, `api` on 4) out of 42 buckets means the workstream path only helps on those 11 tagged visits; the other 31 are bucket-ID only. That is correct: firing a candidate on an unrelated untagged bucket is worse than one expiring unused. 1 consumed + 4 declined shows lookup and the gate did run for 5 of 11 candidates.
- **Duplicate check.** `firstDeliverable` skips a near-duplicate of a recent delivery, leaves the candidate armed, and falls through to the director. There is no evidence this was the dominant blocker, and declining on duplicate would also kill a later legitimate reminder.
- **Gate vs lookup.** The gate ran. 6 still armed after 5 hours with a 12h lifetime is expected: written after the user left that bucket, presentation-suppressed before consume (intentional re-arm), or a 502 before consume/decline (30 of 86 attempts were `http_error` 502 — those correctly leave the candidate armed for retry).

Widening lookup, lifetime, or duplicate policy on n=11 would be fitting noise. A candidate firing when it should not is worse than one expiring unused.

## What was left alone

- Tagging prompt text (a prompt clause already failed; the golden in `ContextBucketPromptAssemblerTests` is untouched).
- Existing `api` rows already in `bucket_workstreams` (not deleted; they just will not spread).
- Pre-model `silence` terminals (`stale_visit`, `pre_model_gate`) and `notification_dropped` after a real decision: those are not transport failures, and rewriting them would change more of the ledger than this defect needs. Abandoned-row reconciliation still records `silence`.
- Candidate lifetime, lookup SQL, and duplicate skip.

## Test plan

- [ ] `cd desktop/macos && xcrun swift build -c debug --package-path Desktop`
- [ ] `xcrun swift test --package-path Desktop --filter 'Context'`
- [ ] Confirm `testGenericLabelsAreRejectedWhileRealProjectNamesAreAccepted` rejects `api` and every other stop-list noun, rejects historical compounds (`cloud-meetings`, `config-management`), accepts `omi` / `hermes` / `omi-api`, and still drops `unknown`
- [ ] Confirm `testEngineRecordsHttp502AsUnresolvedRatherThanSilence` keeps `lifecycleState = failed` and `decisionType = pending`

## Product invariants affected

none

## Failure class (fixes)

Failure-Class: new
