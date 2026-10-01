# EXP-004 — Jev relevance and owner measurement and ramp

**Owner:** dazheng. **Registered:** 2026-09-30. **Review by:** 2026-10-21.
**Decision:** pending; production live Jev flags remain absent (off).

## Fixed treatment and cohort assignment

Model `typesafe/jev-1.13`, gateway `omi:auto:jev-decisions`, relevance question
`relevance_b1` and owner question `owner_a1` are pinned. Discard is strictly
P(discard) > 0.95; owner flip is P(user) >= 0.9. Changing wording, model or
threshold requires a new calibration and protocol.

One SHA256 bucket of `relevance-arm-v1` plus UID assigns consecutive disjoint
ranges: keep-all [0,K), Jev [K,min(100,K+J)), otherwise nano. K is
`CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT` (default 0); J is
`CONVERSATION_RELEVANCE_JEV_PERCENT` (unset means 100 when the existing enable
flag is on, otherwise 0). A UID in `CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST`
is Jev only while enabled and never overrides keep-all. Invalid percentages
resolve every UID to the control nano arm, even with a live flag or allowlist. With K fixed, increasing J retains existing Jev users. Set K
before J: increasing K moves the Jev window and may absorb Jev users into
keep-all; the upper bound is capped at 100.

The production keep-all arm starts 2026-10-01 and runs for at least 14 days
before evaluation. At K=2, membership is the static UID hash window [0,2)
using the `relevance-arm-v1` salt; a user's assignment does not change during
the experiment.

Owner flip is universal when `MEMORY_OWNER_JEV_FLIP_ENABLED` is on; INV-MEM-5
forbids UID cohorts in live owner attribution. `MEMORY_OWNER_JEV_FLIP_PERCENT`
is a universal control: 0 disables scoring, 100 permits it when the flag is on;
unset preserves the flag, and intermediate or malformed values disable it.
There is no owner UID allowlist. Owner *measurement* stays candidate-sampled.

Rules, restores, policy KEEP and the plan gate precede arm treatment. Keep-all
returns policy keep at the ambiguous model tier without calling nano or Jev.
Calendar override remains unchanged. Active experiments store `arm` on every
model-tier record; with all controls off, nano retains its exact legacy record.
Shadow captures nano's raw verdict and reason before calendar override, including
`neighbor_fragment` (nano links to a kept neighbor; Jev cannot reproduce this).
Keep-all has no nano decision, so its agreement cell is `none`. Its counterfactual
nano-discard population must be identified in the readout using an independent,
locked classifier/label set; shadow scores alone are not nano counterfactuals.

## Admission, durability and privacy

Dev declares keep-all percentage 0 and daily caps 60000; prod declares
keep-all percentage 2. Both stages retain daily caps of 60000. Dev runs both
shadows at 100 on the scraped processing hosts (backend-listen, pusher
and the Cloud Run backend service) and retains both live flags on with the live
relevance `CONVERSATION_RELEVANCE_JEV_PERCENT` and owner
`MEMORY_OWNER_JEV_FLIP_PERCENT` pinned to 0 on all four live-flag hosts
(backend-listen, pusher, Cloud Run backend and backend-sync). Unset would enable
live scoring, emptying relevance measurement and excluding the first eight
third-party candidates from owner measurement.
Dev backend-sync and backend-sync-backfill stay at 0: their Cloud
Run revisions have no GMP sidecar/exporter allowlist entry, so their shadow
outcomes and latency would be invisible (see utils/metrics.py). Prod declares
both shadow percentages 100 on backend-listen, pusher and Cloud Run backend,
backend-sync and backend-sync-backfill, with live flags absent, keep-all 2 and
caps unchanged. The production configuration is in its own removable commit.
The Firestore TTL policy on collection group `jev_shadow`, field `expire_at`,
in project `based-hardware` was enabled 2026-10-01 and verified ACTIVE by the
coordinator before the flip; the production flip is no longer held on TTL.
Production sync hosts likewise have no exporter; their persisted measurements
are valid but their attempt/coverage and latency metrics are not scraped.
Readouts must report that visibility limit instead of claiming fleet-wide
failure/latency bars from scraped hosts alone. The new settings are literals, requiring no Secret Manager
pre-bind.

`CONVERSATION_RELEVANCE_JEV_SHADOW_PERCENT` samples the conversation ID with
salt `relevance-shadow-v1`. Only the reached model tier, transcript-only,
non-wake-word, nonempty <=100-word population outside the Jev arm is eligible.
`MEMORY_OWNER_JEV_SHADOW_PERCENT` hashes conversation ID + scoring SHA256
with salt `owner-shadow-v1`. The extraction loop gathers the full eligible batch
before submission, deduplicates full scoring identities, filters by percentage, and
selects the eight lowest hashes per conversation. An owner identity includes
candidate text, the complete `owner_state` (speaker-labelled quotes, title,
overview, source and owner label), question user name, and pipeline subject kind
and entity ID. Identical text with different scoring evidence remains distinct.
Selection is stable under
reordering and independent of extraction position. Only grounded
third-party candidates that the live path did not score (including those beyond
its budget of 8) are eligible. State is assembled from already available values;
workers receive strings and numeric/enum metadata, never conversation objects.

Relevance has a process bound of two queued/active tasks; owner has eight, so
one selected conversation burst fits when the lane is idle. Both use a dedicated,
lazily created ten-worker `jev-shadow` executor. Cross-conversation saturation
and candidates above the per-conversation cap count as `dropped`, never scores.
A 2.5-second task deadline includes queue, Redis, vendor and persistence time.
Admission uses an attempt-owned Redis client with connect/read timeouts at most
0.5 seconds and bounded by the remaining budget; Redis retries are disabled.
The vendor gets one attempt, and Firestore writes disable SDK retries and bound
even the SDK-default commit timeout by racing the transactional call with the
remaining task budget. Redis atomically claims UID + conversation ID +
scoring SHA256 (content SHA256 for relevance) + question version and increments a global UTC-day cap.
`CONVERSATION_RELEVANCE_JEV_SHADOW_DAILY_CAP` and
`MEMORY_OWNER_JEV_SHADOW_DAILY_CAP` default to 60000. Bad caps or unavailable
Redis admit nothing. Dedupe claims persist 60 days, including failed attempts.
No shadow result or failure affects a relevance verdict or persisted memory.

Server-owned records live at `users/{uid}/jev_shadow/{id}`. IDs are the first
32 hex digits of SHA256(`lane|conversation_id|identity_sha|question_version`),
where identity is transcript content for relevance and full scoring identity
for owner. Relevance records
carry score, threshold, arm, raw nano verdict/reason, source, word count, trigger,
served model and question version. Owner records carry candidate and scoring hashes, all three
owner probabilities, pipeline subject kind, source, quote count, user-name-present
boolean, zero-based original extraction `candidate_index` and pre-selection
`eligible_count` integers (unique scoring identities before percentage filtering
and the cap, rather than raw extraction rows), served model and question version. Both have `created_at` and `expire_at`
60 days later. Transactional first-write-wins preserves the original scores
and timestamps on retries. An aborted concurrent transaction writes nothing
and counts as `deduped`, including the SDK wrapped-Aborted exception, rather
than `timeout` or `jev_failed`; the deletion-marker fence stays transactional.
A deadline bounds the worker wait, not an already
started Firestore commit: a valid record may appear after a `timeout` outcome.
Readers include late records and count each `(uid, document_id)` once; do not
add timeout/ok counters to persisted score counts or require an ok outcome for
a record to be valid. Metrics measure attempts and coverage separately.
No transcript, candidate, quote, summary or name is stored or
logged. Client Firestore rules already deny all user subcollections; backend IAM
owns access, and account deletion enumerates and recursively wipes subcollections.
No queries or composite indexes are introduced. The coordinator enabled the
Firestore TTL policy on collection group `jev_shadow`, field `expire_at`, on
2026-10-01 and verified ACTIVE before the flip. The current index reconciler
deliberately cannot enable TTL policies; this PR performs no cloud schema mutations. Inspect aggregate scores and behavior only for other accounts.

Static-label metrics report `ok`, `jev_failed`, `http_429`, `timeout`, `deduped`,
`cap`, `cohort`, `dropped`, `redis_unavailable`; latency includes queue time.
Relevance score bins are 0.5, 0.85, 0.9, 0.93, 0.95, 0.97, 0.99, with the
nano verdict x Jev strict-discard agreement matrix (plus `none`). Owner P(user)
bins are 0.5, 0.7, 0.8, 0.9, 0.95. Drops and caps are part of coverage, not
successful scores. Legacy owner records without `scoring_sha` use text-only
identity; analyze them separately from this full-identity population. Capped/bounded 100% selection is not a census. At 100%, each unique eligible owner candidate has pre-admission inclusion
probability min(1, 8 / unique eligible count); at partial percentages report the
percentage-plus-cap selection probability and actual coverage separately. Check
score and coverage by candidate_index/eligible_count for residual position bias.
Report decision counts separately from unique conversations.

## Acceptance bars

Population and measurement: shadow scores all model-tier, transcript-only, <=100-word conversations (dedupe by conversation+transcript hash; note decisions != conversations because `SYNC_UPDATE`/`CLIENT_FINALIZE` re-assess). Ground truth is (a) David's labels on his OWN account only (no agent or human reads other users' transcripts), stratified on nano verdict x Jev verdict x score band {0.85-0.93, 0.93-0.95, 0.95-0.97, >0.97} and on source, reweighted by inclusion probability (Horvitz-Thompson), with a locked confirmation set that is never used for threshold tuning; (b) behavioral outcomes for the whole population from the randomized keep-all arm (opens, stars, shares, edits, chat citations, deletes within 7 days, restores; restores are heavily censored and used only for a monotonicity check).
Discard GO requires all of: shadow >= 5,000 scored conversations over >= 300 users, Jev failure rate < 5%, p95 latency <= 2.5 s; share of Jev discards (P(discard) > 0.95) judged worth keeping <= 5% on >= 250 stratified David labels; predicted incremental paid-notes spend (conversations nano discards but Jev keeps x measured $0.0024 per kept conversation) <= $25/day or a higher threshold that meets the cap with the same safety bar; and in the production keep-all arm (2% of users, starting 2026-10-01 and running for at least 14 days) the open rate of conversations nano would have discarded is >= 5%. At approximately 18,000 nano discards/day, the arm is expected to keep about 360 extra conversations/day, costing about $0.90/day uncached at $0.0024 each. To stop the arm, set the production keep-all percentage back to 0 and redeploy; conversations kept while users were in the arm remain kept. If the open rate is below 5%, flipping discard is NO-GO (value of keeping is not visible in behavior) and nano stays.
Owner flip GO requires all of: prod shadow P(user) >= 0.9 share among answered third-party candidates within 15-40% (benchmark ~25%; dev showed 74% and must be explained, e.g. by source, empty user name or prompt preamble, before any prod flip); >= 150 David labels stratified by source with Wilson 95% lower bound on precision >= 0.90; flips stay reversible via the stored `attribution_override` record.
Ramp aborts (automatic, any one): Jev failure rate > 5%; p95 latency regresses > 2x; arm actual discard rate differs from the shadow prediction by > 20% relative; empty-title rate among Jev-kept conversations rises; 7-day deletes of kept conversations rise; notes spend per daily active user exceeds cap. Cohorts: 1% -> 10% -> 50% -> 100%, 24 h soak each; the ramp proves operational safety only, quality comes from labels and the keep-all arm.
