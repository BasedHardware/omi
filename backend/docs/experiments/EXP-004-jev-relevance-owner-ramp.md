# EXP-004 — Jev relevance and owner measurement and ramp

**Owner:** dazheng. **Registered:** 2026-09-30. **Review by:** 2026-10-21.
**Decision:** operational ramp authorized; stage 2 (J=10%) started 2026-10-03 after stage 1 soaked 24 h from 2026-10-01 22:46Z, with 14 Jev gateway timeouts and no Jev-attributable 5xx.

## Fixed treatment and cohort assignment

Model `typesafe/jev-1.13`, gateway `omi:auto:jev-decisions`, relevance question
`relevance_b1` and owner question `owner_a1` are pinned. Discard is strictly
P(discard) > 0.80 (lowered from 0.95 on 2026-10-05, see "Threshold
re-measure" below); owner flip is P(user) >= 0.9. Changing wording, model or
threshold requires a new calibration and protocol.

Keep-all selection uses a stable SHA256 bucket of conversation ID and salt
`relevance-keepall-v1`: a random K percent of conversations is kept at the
ambiguous model tier, independently within every account. K is
`CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT` (default 0). No account is selected
into a different policy, consistent with INV-MEM-5: every account uses the
same memory and task authority. Keep-all selection takes precedence for that
conversation. Otherwise the same conversation ID used by keep-all and the
shadow is hashed with salt `relevance-arm-v2` into the Jev range
[K,min(100,K+J)); remaining conversations use nano. J is
`CONVERSATION_RELEVANCE_JEV_PERCENT` (unset means 100 when the existing enable
flag is on, otherwise 0). No account is pinned to an arm: one account can have
keep-all, Jev and nano conversations. `CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST`
is dev dogfooding only, read only when `OMI_ENV_STAGE=dev` and the live flag is
enabled; it never overrides keep-all. Production never reads it, and the runtime
env validator rejects any prod declaration, including an empty or secret binding.
Invalid percentages fail closed to nano outside keep-all; malformed keep-all
configuration selects no conversations. With K fixed, increasing J retains every
conversation already in Jev. Increasing K moves the Jev range's lower and upper
bounds; the upper bound is capped at 100. Keep-all and Jev use independent salts:
at K=2 and J=100, keep-all still wins and non-keep-all conversations whose Jev
bucket is below 2 still use nano. J is the range width, not a promise that 100
bypasses the keep-all experiment.

The production keep-all arm starts 2026-10-01 and runs for at least 14 days
before evaluation. At K=2, each ambiguous model-tier conversation has a stable
2% selection chance using its conversation ID and the `relevance-keepall-v1`
salt. A conversation's assignment is stable; an account can have both selected
and unselected conversations. Arm outcomes are analyzed at the conversation
level, with repeated conversations clustered by user for uncertainty estimates.

Rollback and reprocessing limits: selection is recomputed from the conversation
ID, so setting K back to 0 stops new keep-all treatment but does not pin earlier
assignments; a later `SYNC_UPDATE` reassessment of a previously kept conversation
follows the control (nano) policy, and discards stay recoverable. `arm` lives in
the latest `relevance_decision`, which a later reprocess or merge overwrites, so
analysis uses the shadow records (written at first model-tier exposure) and the
first-processing decision, and excludes conversations reprocessed before readout.

Owner flip is universal when `MEMORY_OWNER_JEV_FLIP_ENABLED` is on; INV-MEM-5
forbids UID cohorts in live owner attribution. `MEMORY_OWNER_JEV_FLIP_PERCENT`
is a universal control: 0 disables scoring, 100 permits it when the flag is on;
unset preserves the flag, and intermediate or malformed values disable it.
There is no owner UID allowlist. Owner *measurement* stays candidate-sampled.

Rules, restores, policy KEEP and the plan gate precede arm treatment. Keep-all
returns policy keep at the ambiguous model tier. It never calls Jev, but it still
calls nano exactly as the control path does (no added spend or latency) and
records nano's verdict and reason without acting on them.
Calendar override remains unchanged. Active experiments store `arm` on every
model-tier record; with all controls off, nano retains its exact legacy record.
Shadow captures nano's raw verdict and reason before calendar override, including
`neighbor_fragment` (nano links to a kept neighbor; Jev cannot reproduce this).
Keep-all records carry nano's would-be verdict, so the nano-discard
counterfactual is measured directly: among keep_all conversations with
`nano_verdict == 'discard'`, compare downstream engagement, deletes and restores
with kept control conversations. A nano failure keeps the conversation and leaves
`nano_verdict` null; those rows are excluded from the counterfactual and reported
as coverage.

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
backend-sync and backend-sync-backfill. Stage 2 enables relevance Jev at J=10 on
those same five hosts after the stage 1 24 h soak from 2026-10-01 22:46Z,
which recorded 14 Jev gateway timeouts and no Jev-attributable 5xx. Keep-all
K=2 remains live; owner-flip flags remain absent, UID allowlists remain absent,
and caps are unchanged. Keep-all takes
precedence on each conversation. Because keep-all and Jev use independent salts,
their assignments can overlap; non-keep-all conversations in the Jev bucket
range [2,12) use Jev and the remaining roughly 88% stay on nano. Nano remains
the large control arm, but this is not a separate matched nano-only cohort. The
production configuration is in its own removable commit.
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
Relevance score bins are 0.5, 0.7, 0.75, 0.8, 0.85, 0.9, 0.93, 0.95, 0.97, 0.99
(0.7-0.8 added 2026-10-05 so the predicted discard rate at the current cutoff
is readable from buckets), with the nano verdict x Jev strict-discard agreement matrix (plus `none`). Owner P(user)
bins are 0.5, 0.7, 0.8, 0.9, 0.95. Drops and caps are part of coverage, not
successful scores. Legacy owner records without `scoring_sha` use text-only
identity; analyze them separately from this full-identity population. Capped/bounded 100% selection is not a census. At 100%, each unique eligible owner candidate has pre-admission inclusion
probability min(1, 8 / unique eligible count); at partial percentages report the
percentage-plus-cap selection probability and actual coverage separately. Check
score and coverage by candidate_index/eligible_count for residual position bias.
Report decision counts separately from unique conversations.

## Threshold re-measure (2026-10-05)

At 0.95 the live arm discarded about 3% of model-tier conversations against
about 90% for nano, and on the owner's 2026-10 labels (60 cards in three
waves; the random wave was 20 of 20 noise) almost all of Jev's extra keeps
were noise. The threshold was re-measured offline on the owner's account only:

- Tuned on 55 decided 2026-10 labels (9 kept); evaluated once on 77 decided
  2026-09-23 labels (20 kept) that were never used for tuning.
- Held-out: nano lost 15-17 of 20 kept conversations and kept 4-5 of 57 noise;
  Jev `relevance_b1` at 0.70 lost 7 and kept 7; at 0.80 lost 3 and kept 10.
  Jev AUC was about 0.85 on both sets. Reworded "own voice" questions and added
  speaker metadata did not beat `relevance_b1` on the held-out set.
- 0.80 was picked after seeing the held-out set (0.70 was the pre-declared
  value), favouring fewer lost keeps. With 29 kept conversations in total the
  loss rate is uncertain.
- Population (shadow records since 2026-10-03, 30.8k decisions, 995 users):
  Jev discards 62.9% at 0.80 against nano's 89.6%. Predicted incremental notes
  spend at J=100 is about 5.2k conversations/day x $0.0024 = about $12/day,
  inside the $25/day cap (0.95 would have been about $36/day).
- Deviation from the acceptance bars below: fewer than 250 stratified owner
  labels and the keep-all readout (due about 2026-10-15) is not in. The owner
  approved shipping the re-measured threshold at the current J=10 stage; the
  ramp's abort criteria still apply, with the shadow-predicted discard rate
  now taken at 0.80.

## Acceptance bars

Population and measurement: shadow scores all model-tier, transcript-only, <=100-word conversations (dedupe by conversation+transcript hash; note decisions != conversations because `SYNC_UPDATE`/`CLIENT_FINALIZE` re-assess). Ground truth is (a) David's labels on his OWN account only (no agent or human reads other users' transcripts), stratified on nano verdict x Jev verdict x score band {0.80-0.85, 0.85-0.93, 0.93-0.95, 0.95-0.97, >0.97} (the 0.80-0.85 band added with the 2026-10-05 threshold change) and on source, reweighted by inclusion probability (Horvitz-Thompson), with a locked confirmation set that is never used for threshold tuning; (b) behavioral outcomes for the whole population from the randomized keep-all arm (opens, stars, shares, edits, chat citations, deletes within 7 days, restores; restores are heavily censored and used only for a monotonicity check).
Discard GO requires all of: shadow >= 5,000 scored conversations over >= 300 users, Jev failure rate < 5%, p95 latency <= 2.5 s; share of Jev discards (P(discard) > the live threshold, 0.80 since 2026-10-05; 0.95 before) judged worth keeping <= 5% on >= 250 stratified David labels; predicted incremental paid-notes spend (conversations nano discards but Jev keeps x measured $0.0024 per kept conversation) <= $25/day or a higher threshold that meets the cap with the same safety bar; and in the production keep-all sample (2% of ambiguous model-tier conversations, starting 2026-10-01 and running for at least 14 days) the open rate of conversations nano would have discarded is >= 5%. At approximately 18,000 nano discards/day, the sample is expected to keep about 360 extra conversations/day, costing about $0.90/day uncached at $0.0024 each. Analyze these outcomes per conversation and account for within-user clustering. To stop the sample, set the production keep-all percentage back to 0 and redeploy; conversations already kept remain kept and are not retroactively discarded. If the open rate is below 5%, flipping discard is NO-GO (value of keeping is not visible in behavior) and nano stays.
Owner flip GO requires all of: prod shadow P(user) >= 0.9 share among answered third-party candidates within 15-40% (benchmark ~25%; dev showed 74% and must be explained, e.g. by source, empty user name or prompt preamble, before any prod flip); >= 150 David labels stratified by source with Wilson 95% lower bound on precision >= 0.90; flips stay reversible via the stored `attribution_override` record.
## Live relevance ramp and coordinator runbook

Ramp by conversation: **1% -> 10% -> 50% -> 100%**, with **24 h soak per
stage** and K fixed at 2. Stage 2 (J=10) started 2026-10-03 after stage 1
soaked 24 h from 2026-10-01 22:46Z, recording 14 Jev gateway timeouts and no
Jev-attributable 5xx. It is live with keep-all K=2 on the five processing
hosts; keep-all wins any overlap, and all remaining conversations outside the
Jev range use nano. Owner-flip flags and the UID allowlist remain absent. The
coordinator ships each next env stage in a separate tiny PR. The
ramp proves operational safety; the keep-all arm remains the engagement evidence.
The 250-label bar above is not met by this implementation and must not be
reported as passed. The coordinator's 2026-10-02 decision authorizes this
operational ramp with restores/deletes monitored while labels and the 14-day
keep-all readout remain outstanding quality evidence.

Automatic abort criteria (any one): Jev failure rate > 5%; p95 latency regressing
> 2x against the preceding stage; actual arm discard rate differing from the
matched shadow prediction by > 20% relative; empty-title rate among Jev-kept
conversations rising; 7-day deletes of Jev-kept conversations or restores of
Jev-discarded conversations rising; notes spend per DAU exceeding the cap.
Track both deletes and restores across Jev-kept/discarded conversations and
cluster repeated decisions by conversation and account. Discards are recoverable
through Show discarded / restore; restoring records `sync_relevance_user_kept`,
which takes precedence over later model decisions. These are rollout gates for
the coordinator's monitoring, not automatic control implemented by this PR.
At shadow prediction zero, any nonzero actual discard rate aborts; do not divide
by zero. Compare matched source/word-count/model-tier populations. Define the
rise baselines and notes spend per DAU cap before promotion; the existing $25/day
incremental-notes bar does not itself define a per-DAU cap.

On **gke/backend-listen**, **gke/pusher**, **cloud_run/services/backend**,
**cloud_run/services/backend-sync**, and **cloud_run/services/backend-sync-backfill**,
add the following exact entries to each host's `env` map in
`backend/deploy/runtime_env/prod.overlay.yaml` for stage 1:

```yaml
CONVERSATION_RELEVANCE_JEV_ENABLED:
  value: 'true'
  category: rollout
CONVERSATION_RELEVANCE_JEV_PERCENT:
  value: '1'
  category: rollout
```

For stages 10, 50 and 100, change only the percent `value: '1'` -> `'10'` ->
`'50'` -> `'100'` on those same five hosts; the enable entry stays `'true'`.
Do not add these flags to backend-integration or change owner-flip flags.
For each stage, compose `backend/deploy/runtime_env.yaml` with
`python3 backend/deploy/compose_runtime_env.py`. In both production Helm values
files (`backend/charts/backend-listen/prod_omi_backend_listen_values.yaml` and
`backend/charts/pusher/prod_omi_pusher_values.yaml`), add the matching env list
at stage 1, then change only the percent literal at later stages:

```yaml
- name: CONVERSATION_RELEVANCE_JEV_ENABLED
  value: "true"
- name: CONVERSATION_RELEVANCE_JEV_PERCENT
  value: "1"
```

Update the currently-off prod assertions in
`test_backend_runtime_env_validator.py`, then regenerate the feature-flag registry
with `python3 scripts/render_feature_flag_registry.py`. Validate via
`bash backend/scripts/pre-deploy-check.sh` and deploy the Cloud Run, listen and
pusher workflows serially. Verify the two live env values on all five hosts;
source declarations alone do not prove serving state. Rollback sets enabled to
`false` (and percent to `0`) on all five hosts and redeploys; it does not
retroactively rewrite conversation decisions. Reprocessing follows the current
policy, while explicit restores stay protected.

### Provider bindings and measurement limits

Both the live relevance helper and the prod shadow call `ask_jev` in
`utils/llm/jev_client.py`: `POST /v1/systemone`, model
`omi:auto:jev-decisions`. Each processing host already declares the derived
`OMI_LLM_GATEWAY_URL` and secret `OMI_LLM_GATEWAY_SERVICE_TOKEN`. Jev does not
require `OMI_LLM_GATEWAY_FEATURE_MODE` or a backend-host OpenRouter key; it always
uses the gateway. The generated lane in `llm_gateway/gateway/config_loader.py`
pins `typesafe/jev-1.13`, provider `openrouter`, one provider attempt and no
fallback. The production gateway Helm values bind `OPENROUTER_API_KEY` and
`OMI_LLM_GATEWAY_SERVICE_TOKEN` from the gateway secret. No missing source
binding was found; secret payloads, installed route and serving reachability
remain deployment checks and are not verified by this code-only PR.

Live calls record `omi_jev_decision_total` and latency for
`conversation_relevance`; shadow calls suppress those metrics. Sync and backfill
have no exporter, so scraped failure/latency bars cover only listen, pusher and
Cloud Run backend. At J=100 very little nano shadow population remains; preserve
pre-ramp predictions and the parallel keep-all shadow instead of treating a
shrinking shadow sample as fleet-wide proof. The coordinator must close the sync
visibility and monitoring/cap definition gaps before claiming automatic fleet
abort coverage or promoting on those gates.
