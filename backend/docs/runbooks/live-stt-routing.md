# Live STT routing and Soniox runway

## Controls and evidence contract

Production merges in `STT_ROUTING_MODE=shadow`, `STT_ROUTING_ON_PERCENT=0`.
The configured fallback order is Parakeet window → Soniox → Modulate → retired
Deepgram. Parakeet allocation/capacity remain independently approved controls;
do not copy an older allocation percentage from this runbook. The static reorder
avoids exposing shadow and rollback sessions to the known Modulate brownout.
The active router still chooses the cheapest capable healthy target, with no
artificial diversification or expensive-provider probes.

`LiveLegOutcome.settle` emits a serving decision's fallback and router observation
once, synchronously. The source cause survives successor rejection and cleanup.
Liveness reads emit neither. Normal client/owner close is success if text was
seen, otherwise censored. Teardown snapshots the published death latch before
closing: an already-dead provider counts even if the monitor has not claimed it;
transport errors that begin after this fence remain censored. A provider death is counted without a speech minimum
when the serving owner replaces/rejects it or exhausts recovery. A pending hop
without successor text settles as degraded after 30 seconds, with no socket or
audio change. Established fallback reasons stay stable, including quota/auth;
health retains the corresponding typed account reasons. Soniox 408 uses censored `soniox_request_timeout`; 400 no-audio uses
`soniox_idle_timeout`. Neither opens a provider circuit for all users, including connect rejection.
Repeated Soniox 408 connect rejections deliberately do not create a cross-session
bench: this cause cannot distinguish a provider outage from client/input timing.
Each connection still falls through to the next provider. Accept that repeated
connect cost/latency risk; inspect its reason counter and transcript/latency SLIs
and withdraw the endpoint manually if the aggregate shows an outage.
Local VAD and other explicitly censored input/configuration failures also release
circuit admission without accumulating provider failures.

`omi_stt_cost_routing_settlements_total{target,outcome,reason,path}` is the
expected observation count from that seam (`path=close|failover|connect`). Its
sum over path must equal `omi_stt_cost_routing_observations_total` by
instance/target/outcome/reason. This comparison covers exactly the managed
router population; legacy/PTT fallback events are not extra router samples.
A direct acknowledgement from the observation writer feeds the single
`omi_stt_cost_routing_emission_ack_errors_total` counter; exceptions or missing
acknowledgements increment it. This checks acknowledgement only: neither this
counter nor the paired emissions detects omitted terminal paths or consistently
wrong classification, and neither proves Redis persistence. Redis drop counters and
`omi_stt_cost_routing_votes_total{target,scope,result}` prove whether classified
evidence reached shared state (`applied|user_cap|window_full|generation|stage`).

State uses `omi:live-stt:cost-v8:<stage>:<32-hex identity>:<target>:<bounded-language>`
with recovery lease keys under the same cost prefix. Fleet keys split two
`omi:live-stt:fleet-v2:<stage>:<32-hex identity>` scopes: selection bench,
recovery probe and score keys digest the family, actual endpoint and
credential, while the account bench key digests only family and credential, so
the credential-wide quarantine spans every custom endpoint but survives an
endpoint rotation that resets selection/score/probe and cost state. Registry
targets with a custom `endpoint` write and read their own endpoint-scoped
selection/score/probe partitions — a sibling endpoint's serve deaths, connect
refusals and transcript outcomes never bench the configured default or other
siblings, while the credential-wide account bench still protects all of them.
With `STT_ROUTING_MODE=off` snapshots answer a neutral score and merge only
family account deadlines, ignoring but not erasing selection state. The stage
comes from `OMI_ENV_STAGE` (unrecognized values map to `unknown`, never prod;
`PROVIDER_MODE=offline` still yields `offline`);
a changed endpoint, credential or stage starts its scoped state
with no migration or backfill of older namespaces, which are never read. Raw
URLs and keys never appear in Redis paths, logs or metrics. A pod's in-memory
health views reset when that identity changes. Process-local selection
breakers differ: they retain connect/serve outage evidence across credential
rotation for an unchanged endpoint — credential rotation clears
account/quota state only, an endpoint change starts fresh selection state
while the unchanged credential's account protection remains, and a stage
change starts fresh scoped state. A custom endpoint's serve death opens
that endpoint's local target breaker and does not bench the family default. Do not
reuse older-namespace evidence. At stage 100, one hashed user contributes at most three
success/failure outcomes in a five-minute Redis-time window. Windows hold at
most 2,048 ordinary fingerprints (above 1,500 at 10x 1,800 sessions/hour),
plus an eight-fingerprint outage reserve. At saturation, eight distinct new
users failing without an intervening classified success bench the target. Every
success resets this reserve, even if its normal vote is capped; one repeated
caller cannot fill it, and it cannot fill without benching. This reserve does
not feed failure-only samples into CUSUM or refill existing user budgets. Any
`window_full` remains a rollout stop because normal brownout evidence is sampled. Healthy
state keys expire after 900 idle seconds; benched/trial state persists to prevent
expiry bypassing staged recovery and holds no healthy-window fingerprint list. Raw observation counts remain uncapped for
reconciliation. Trials retain their separate user votes, generation fences,
5→25→100 shares, and exponentially increasing cooldown. Trial promotion needs
30 admitted outcomes from at least 10 witnesses after 300 seconds for the 5%
step, and 60 admitted outcomes from at least 20 witnesses after 600 seconds for
the 25% step; a completed admitted window before the dwell holds at its stage.
Redis CAS enforces all
of this fleet-wide. Bench writes are one atomic Lua update — an active account
quarantine rejects a selection write, same-kind writes keep the longest
deadline — and expired cleanup is a compare-delete that re-checks the observed
value inside Redis before removing it, so a renewed bench survives a read/delete
race. Shared snapshots refresh off connect, normally every five
seconds, under a 75 ms deadline; local fallback retains known benches.
Every refresh reads all registry targets across the closed supported-language
vocabulary plus `all`, so a language bench is honored on its first request even
without prior interest. Freshness is per `(target, language)`; an unread
language raises `CostHealthUnavailable` instead of reporting stage 100, which
the chain treats as a fail-open: non-canary sessions keep the filtered static
order, while canary sessions keep their permitted registry target routes with
the exception's conservative states demoting known restricted entries (a
generic router error carries no snapshot and keeps configured order).
Per-target language
comparisons are counted in
`omi_stt_cost_routing_language_state_total{target,comparison}` with
`agree|language_restricted|global_restricted|unknown|stale`.

Every dial — proposal candidates, last resorts and the static fallback in all
modes — passes the same permission filter: actual engine match, capability for
the requested and expected languages, sticky registry ramp (including the
`parakeet-window` minimum of registry percent and window allocation), and
active account quarantine. If filtering empties the chain the connect raises
`ProviderChainUnavailable` with a bounded retry and counts
`omi_stt_cost_routing_no_permitted_target_total`. An invalid registry cannot
prove permissions, so a managed session gets the typed chain-unavailable and a
`router_error` fail-open rather than a default that could reopen a withdrawn
target.

The [architecture](../../utils/stt/ARCHITECTURE.md#serving-owned-health-evidence-cost-v8)
has the taxonomy, registry and second-endpoint example, exact gate, and
reproducible calibration. The gate stays 8%. In gate simulation, every
realistic-floor row has zero false benches in 400k sessions; 40%/60%/100%
provider errors bench at median 20/13/8 and p95 48/21/8 sessions. At 62 sessions
per five minutes that is about four minutes at the 40% p95, plus settlement
and cache delay. The rate must be representative admitted votes, not one
client's repeated reconnects. These are synthetic bounds, not prod acceptance.

## Minimum shadow go/no-go (normally 60–120 minutes)

Start the observation window after every listen pod runs the same new image and
has been scraped. Do not reset shared state mid-window. Require at least 60
minutes plus the following positive coverage; elapsed time alone never passes:

1. At least 500 proposals, 100 settled classified Parakeet legs, and 100 Soniox
   legs. Inspect every observed language group and all provider-failure reasons.
   The new seam's real-parser/receiver tests must be green on the deployed SHA.
2. No persistent opened-minus-settled-minus-open lifecycle gap; exactly zero
   emission acknowledgement errors, evidence exceptions, unavailable
   proposals and all-degraded selections. No Redis result drops, saturated
   evidence windows, router/cache errors or unknown/stale snapshots.
3. Parakeet and Soniox global stage 100 on every fresh pod, with no unexplained
   language bench. Proposal shares match current allocation and capabilities;
   no healthy admitted Parakeet primary is diverted to a costlier target.
4. Modulate either demonstrates its bench/5% recovery on real fallback evidence,
   **or is explicitly withdrawn with registry `ramp_percent=0` in the on config**.
   Static Soniox-first order can legitimately yield too little Modulate traffic
   to warm its new namespace. Unknown/untested Modulate is not permission to
   send it new primary traffic. Do not manufacture probe traffic to qualify it.
   A complete registry override must retain Parakeet and Soniox entries; after
   active selection their registered Modulate sibling cannot reappear as a
   static tail. Router-error fail-open keeps permitted registry targets for
   canary sessions and the filtered static chain otherwise.
5. Transcript-success, no-text share, first-text latency, window capacity and
   GPU pressure remain within the conditions below. Confirm the existing
   transcript-success alert is evaluated and routed to the live contact point.

If low-volume coverage is missing after two hours, keep that target withdrawn
or remain shadow. This is a bounded first canary, not 24-hour reliability proof.
A new Modulate endpoint later enters through its own registry ID and 5% ramp;
its evidence must never reuse the old endpoint's identity or state.

## Exact PromQL

Use `job="backend-listen-metrics"`, and a window containing only the new image.
The **emission acknowledgement check** below must be zero; it is not an
independent correctness oracle. Missing metrics are failure of coverage, not zero.
The paired-counter difference is also useful by instance/target/reason, but a
scrape reads separate collectors at slightly different instants: a transient
difference during active settlement can be a scrape race. Require that the
one-minute minimum paired difference is zero, and investigate any persistent
mismatch; do not mistake `increase()` extrapolation or a first scrape for lost
evidence.

```promql
sum(omi_stt_cost_routing_emission_ack_errors_total{job="backend-listen-metrics"})
min_over_time((sum(abs(
  sum by (instance, target, outcome, reason) (omi_stt_cost_routing_settlements_total{job="backend-listen-metrics"})
  -
  sum by (instance, target, outcome, reason) (omi_stt_cost_routing_observations_total{job="backend-listen-metrics"})
)))[1m:15s])
sum(increase(omi_stt_cost_routing_evidence_errors_total{job="backend-listen-metrics"}[1h]))
sum by (target, path, outcome, reason) (increase(omi_stt_cost_routing_settlements_total{job="backend-listen-metrics"}[1h]))
sum by (from_mode, reason, outcome) (increase(omi_fallback_total{job="backend-listen-metrics",component="stt_live_session"}[1h]))
```

The last query includes legacy/PTT traffic and uses provider-family labels;
endpoint-specific equality is checked by the paired-counter difference. For managed failure
settlements, account labels map budget→quota and rejected-auth→auth. Connect
settlements belong to `stt_selection`, terminal deaths to `stt_live_session`.

Deaths are eligible at the first serving claim, not at a read-only liveness
poll. Explicit client/application disconnect, inactive state or shutdown at
that claim excludes the death and suppresses its fallback emission. A claim
already made with a connected client remains valid after later departure.
Existing text remains one success; otherwise the excluded leg settles as
censored no-text. Repeated claims/close/validation cannot revive a settled leg.
The backend cannot recover the ordering of an unclaimed raw death and client
departure retrospectively.

For a fixed accepted-socket cohort and bounded provider reasons:
`provider_failure observations = settled nonterminal hops + connected terminal deaths`.
Terminal deaths now also emit fallback to `unavailable`, so do not add their
session-level terminal counter to the whole fallback total again. Connect-chain
exhaustion remains a separate surface and can be zero for a serving terminal
Soniox death. Excluded deaths have no provider-failure or hop emission; read:

```promql
sum by (target, reason, boundary) (increase(omi_stt_cost_routing_ignored_deaths_total{job="backend-listen-metrics"}[1h]))
sum by (component, from_mode, to_mode, reason, outcome) (increase(omi_fallback_total{job="backend-listen-metrics",component=~"stt_selection|stt_live_session"}[1h]))
sum by (provider, outcome, phase) (increase(omi_live_stt_terminal_failures_total{job="backend-listen-metrics"}[1h]))
sum(increase(omi_stt_chain_exhausted_total{job="backend-listen-metrics"}[1h])) or vector(0)
```

The ignored counter covers a claimed death excluded by lifecycle, not every
late transport-close symptom. Its labels are registered target (<=16), bounded
reason vocabulary and boundary (`client_gone`/`owner_teardown`), preinitialized.
Require Modulate provider-failure counts to match the managed serving cohort
of selection plus live/terminal fallback emissions per reason before `on`.
The paired counters alone can agree while both classify client churn wrongly.
New `cost-v8`/`fleet-v2` state discards all earlier namespaces' post-client
failures and strikes; it does not migrate or backfill those samples. The
sequential 8% gate and healthy vote budgets stay unchanged; trial vote budgets
are tightened to admitted outcomes only.

Independent lifecycle oracle: the chain counts `opened` when handing off a
connected managed leg (including same-provider replacement), transport release
decrements `open`, and terminal settlement separately counts `settled`. Rejected
connects that never hand off are excluded from all three. The per-pod/target
difference must return to zero; allow the existing 30-second deferred hop
settlement and scrape races, but **no nonzero gap persisting two minutes**. A
missing settlement after transport release grows this gap even if acknowledgement
errors stay zero. This detects lifecycle coverage, not wrong reason attribution;
retain real-object tests and provider-reason/session-SLI inspection for that.

```promql
sum by (instance, target) (omi_stt_managed_legs_opened_total{job="backend-listen-metrics"})
- sum by (instance, target) (omi_stt_managed_legs_settled_total{job="backend-listen-metrics"})
- sum by (instance, target) (omi_stt_managed_legs_open{job="backend-listen-metrics"})

min_over_time((abs(
  sum by (instance, target) (omi_stt_managed_legs_opened_total{job="backend-listen-metrics"})
  - sum by (instance, target) (omi_stt_managed_legs_settled_total{job="backend-listen-metrics"})
  - sum by (instance, target) (omi_stt_managed_legs_open{job="backend-listen-metrics"})
))[2m:15s]) > 0
```

Coverage, admitted votes and health evidence:

```promql
sum(increase(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h]))
sum by (target) (increase(omi_stt_cost_routing_observations_total{job="backend-listen-metrics",outcome=~"success|provider_failure"}[1h]))
sum by (target, scope, result) (increase(omi_stt_cost_routing_votes_total{job="backend-listen-metrics"}[1h]))
sum by (target) (increase(omi_stt_cost_routing_observations_total{job="backend-listen-metrics",outcome="provider_failure"}[1h])) / clamp_min(sum by (target) (increase(omi_stt_cost_routing_observations_total{job="backend-listen-metrics",outcome=~"success|provider_failure"}[1h])), 1)
sum by (kind) (increase(omi_stt_fleet_health_write_dropped_total{job="backend-listen-metrics"}[1h]))
```

Global stage and snapshot integrity (minimum and maximum must agree; unknown
NaN is never healthy). A language transition can restrict one language without
changing the global gauge; inspect the separate transition scope:

```promql
min by (target) (omi_stt_cost_routing_stage{job="backend-listen-metrics"})
max by (target) (omi_stt_cost_routing_stage{job="backend-listen-metrics"})
min by (target) (omi_stt_cost_routing_state_known{job="backend-listen-metrics"})
max(time() - omi_stt_cost_routing_snapshot_timestamp_seconds{job="backend-listen-metrics"})
count(omi_stt_cost_routing_snapshot_timestamp_seconds{job="backend-listen-metrics"} != omi_stt_cost_routing_snapshot_timestamp_seconds{job="backend-listen-metrics"}) or vector(0)
sum by (target, event, scope) (increase(omi_stt_cost_routing_events_total{job="backend-listen-metrics"}[1h]))
```

Require snapshot age <15 seconds, no NaNs, known=1 for traffic-enabled targets.
A deliberately withdrawn unused target can remain unknown; exclude it explicitly
when evaluating that requirement. Series are preinitialized before traffic so
post-first-scrape transitions and observations are visible to `increase()`.

Would-have-changed-primary breakdown and guard counters:

```promql
sum by (agreement, static_primary, proposed_primary) (increase(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h]))
sum by (proposed_primary) (rate(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h])) / scalar(sum(rate(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h])))
sum(increase(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics",proposed_primary="unavailable"}[1h])) or vector(0)
sum(increase(omi_stt_cost_routing_all_degraded_total{job="backend-listen-metrics"}[1h])) or vector(0)
sum by (reason) (increase(omi_stt_cost_routing_fail_open_total{job="backend-listen-metrics"}[1h]))
sum(increase(omi_stt_cost_routing_no_permitted_target_total{job="backend-listen-metrics"}[1h])) or vector(0)
sum by (target, comparison) (increase(omi_stt_cost_routing_language_state_total{job="backend-listen-metrics"}[1h]))
```

`static_primary` is the configured eligible nomination before local circuit and
connect attempts, not the eventual serving provider. The pair metric runs in
shadow and on; read the actual runtime mode. Positive proposal coverage is
required before interpreting an absent/zero guard series.

User-facing SLIs and silent-provider detection:

```promql
sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome="transcribed"}[15m])) / clamp_min(sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[15m])), 1)
sum by (provider, language, outcome) (increase(omi_stt_leg_transcript_outcome_total{job="backend-listen-metrics"}[15m]))
histogram_quantile(0.95, sum by (le) (rate(omi_stt_window_first_text_seconds_bucket{job="backend-listen-metrics"}[15m])))
sum(increase(omi_stt_window_admissions_total{job="backend-listen-metrics",outcome="overflow"}[15m])) / clamp_min(sum(increase(omi_stt_window_admissions_total{job="backend-listen-metrics"}[15m])), 1)
histogram_quantile(0.95, sum by (le) (rate(omi_stt_window_post_seconds_bucket{job="backend-listen-metrics"}[15m])))
```

No-text is a mandatory separate SLI, never gate failure evidence. An accepted
non-window provider that returns no words indefinitely has no new automatic
per-session rescue. Continuing speech triggers the diagnostic no-text deadline;
completed sessions feed `omi-live-transcription-success-low` (existing <90%,
>=50 counted sessions/5m, five-minute dwell page). Quiet unfinished streams do
not establish a vendor fault and remain outside this automatic detector.

## Recommended on ramp and abort

After the checklist passes, configure `on` at **5% for at least 60 minutes and
100 classified canary sessions**, then **25% for at least 60 minutes and 300**,
then **100% with at least two hours of attended observation**. Count actual
router allocation with the new intent-to-treat cohort metric below. The arm is
captured before initialization: an on-arm session that fails open or cannot
connect still counts in the on arm. Custom-STT, BYOK and multi-channel sessions
are excluded. `too_short` remains visible but outside the success denominator.

```promql
sum by (arm) (increase(omi_stt_cost_routing_canary_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[1h]))
sum by (arm) (increase(omi_stt_cost_routing_canary_outcome_total{job="backend-listen-metrics",outcome="transcribed"}[15m])) / clamp_min(sum by (arm) (increase(omi_stt_cost_routing_canary_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[15m])), 1)
```

Extend dwell until the on arm reaches the exposure floor; do not substitute
shadow proposals or window-allocation counts for actual router canary sessions.

Abort to shadow/zero for a persistent lifecycle gap, any emission acknowledgement error or evidence exception; any
unavailable/all-degraded proposal; sustained Redis/write/cap errors; or a
Parakeet/Soniox bench unexplained by actual provider failures. Abort for a >2
percentage-point drop in transcript success from the pre-ramp baseline over
15 minutes with >=100 counted sessions, or <95% absolute; first-text p95 >=30s;
window POST p95 >=2s; or >1% capacity overflow for ten minutes. Compare language
mix and absolute counts; use existing GPU/backfill capacity gates as well.
Apply the transcript abort to the on arm as well as the whole fleet; compare
with the control arm and the pre-ramp baseline. At small sample sizes these are
operational gates, not a statistical proof of non-inferiority.

Kill switch: set `STT_ROUTING_ON_PERCENT=0` or `STT_ROUTING_MODE=shadow` (`off`
also restores static selection; snapshots go neutral and read only family
account benches — a stale selection bench cannot shed the chain, and shared
account quarantine stays enforced in
every mode, so `off` never reopens a credential another pod withdrew). Apply
through the coordinator's config PR and
normal deployment; this is not an instant process-local env mutation.
`PARAKEET_WINDOW_ALLOCATION_PERCENT=0` independently withdraws the window leg.
Keep chart + prod overlay aligned, then regenerate `backend/deploy/runtime_env.yaml`
with `python3 backend/deploy/compose_runtime_env.py`. Do not write routing state
through dev: dev shares production Redis/Firestore.

## Soniox runway

`SONIOX_MONTHLY_CEILING_USD` sets the monthly alert ceiling; zero disables
the poller. The production value is configured in the listen chart and
runtime env. No automatic top-up or hard paid-traffic cutoff occurs. The
hourly poller prefers Soniox's current-month `/v1/usage/summary` dollar cost.
The existing backend-listen `SONIOX_API_KEY` needs the Soniox **Usage and
limits** permission for this read. If the API read fails, the poller estimates
from Omi-metered Soniox audio seconds times
`SONIOX_ESTIMATED_USD_PER_HOUR`; that estimate can undercount if Redis was
unavailable or if Soniox charges for audio outside this listen path. Check
`omi_soniox_usage_source{source="vendor"}` and the sample timestamp before
acting on the amount. The 70% and 90% Telegram alerts explicitly say **top
up Soniox**. Compare the configured ceiling with the real Soniox account
balance during an incident; the ceiling itself does not fund the account.

```promql
max(omi_soniox_month_spend_usd{job="backend-listen-metrics"}) / clamp_min(max(omi_soniox_month_ceiling_usd{job="backend-listen-metrics"}), 1)
max(omi_soniox_usage_source{job="backend-listen-metrics"}) by (source)
time() - max(omi_soniox_usage_sample_timestamp_seconds{job="backend-listen-metrics"})
```

## Operator reset

After repairing a credential or provider outage, inspect the local and
fleet circuit metrics. Run `python3 backend/scripts/stt/reset_fleet_provider.py
soniox` in the intended environment for a dry run. An approved operator may
repeat with `--execute` to delete only that named provider's recent fleet
score, account/selection bench and recovery probe keys. This legacy reset
does not clear the new cost-gate namespace; let its staged recovery proceed
after repairing the provider. The script refuses
more than 1,000 matching keys and uses short Redis socket deadlines. It does
not reset process-local circuits; those recover on their existing cooldown,
or after an operator controlled listen restart. Never point the script at a
different environment to clear a production alert.


## Router-on readiness controls (default off)

`STT_PAID_SPILLOVER_BUDGET_ENABLED=false` preserves existing selection. When
true, router-on sessions encountering Parakeet capacity refusal must obtain a
fleet admission before promoting a paid route. Redis TIME and one atomic Lua
operation enforce a fixed UTC-minute budget across pods; aliases/endpoints on
the same provider account share the budget. Defaults are 30 promotions each
for `STT_PAID_SPILLOVER_SONIOX_PER_MINUTE`,
`STT_PAID_SPILLOVER_MODULATE_PER_MINUTE`, and
`STT_PAID_SPILLOVER_DEEPGRAM_PER_MINUTE` (range 0–10000). Zero refuses
promotions. Redis faults or budget denial restore the configured order and
emit `omi_stt_paid_spillover_admissions_total{provider,outcome}` with outcomes
`admitted`, `denied`, `unavailable`. This limits additional router promotions;
the static chain may still require a paid dial. A minute boundary can admit
two adjacent budgets in a short interval. Qualify paid concurrency, retry and
billing headroom independently before enabling router traffic.

`STT_NO_TEXT_RESCUE_ENABLED=false` preserves existing first-text handling.
Enabling it also requires `STT_FAILOVER_RECOVERY_ENABLED=true`; the choice and
`STT_NO_TEXT_RESCUE_SECONDS` are pinned when the managed session is created.
The default 60-second lease (range 5–120) bounds both paid wall time and paid
admitted audio, including replay and successor switches, for one ambiguous
no-text interval per listen session. A successor transcript records proof but
does not renew the lease. At expiry or audio-budget refusal, the owner tries
windowed Parakeet once, retaining unanswered capture and applying the normal
replay/epoch fences. This policy retirement never benches the paid provider.
If cheap permission/capacity is unavailable, recovery terminates explicitly;
it cannot quietly extend the paid lease. Returned cheap decoding suppresses
further first-text/empty-streak rescues for the session. Normal transport
failures still use the configured recovery path. Empty output does not establish
that audio is noise. Before a lease is spent, the gated window deadline rearms
after emitted text so later speech without progress can also trigger rescue.

`omi_stt_no_text_rescue_audio_seconds_total{provider}` measures admitted paid
rescue audio; `omi_stt_no_text_rescue_total{outcome}` counts starts and completed
intervals, distinguishing `successor_text` from `unproven`. Starts from sessions
that leave before lease completion remain censored; these metrics are not an
invoice or a transcript-quality score. For a synthetic one-hour Soniox
remainder, the declared $0.0754/audio-hour rate implies $0.0754 without a
lease versus at most $0.001257 for 60 paid audio seconds, followed by cheap
processing. Billing increments and costs of genuine later transport failures
are separate. Existing production counters do not join deadline causes to
successor duration; do not claim historical savings from them.

The monitoring chart's `alerts/live-stt.json` and combined `alert-rules.json`
contain independent terminal-after-text, mid-session terminal, paid-capacity,
combined overflow/batch-pressure, POST-latency, replay-continuity, lifecycle,
persistence, snapshot and stage-readiness rules. Any-text headline success
remains its existing limited SLI. Deploy and test notification delivery through
the monitoring release process before rollout; committing rules does not make
them live. Lifecycle/replay rules document their configured-chain/recovery
prerequisites. The #20391 terminal-after-text emitter also requires the pinned
recovery flag; its dedicated alert is dormant while that flag is off. The
independent mid-session terminal rule covers every path. Never pool lifecycle
counters across instances or targets.

Local limiter qualification (disposable Redis, no cloud data):

```bash
printf '%s\n' tests/integration/test_paid_spillover_redis.py > .local/redis-tests.txt
OMI_OWNED_PID_FILE="$PWD/.local/owned-pids.txt" \
BACKEND_PYTEST_MARK_EXPR=integration \
BACKEND_UNIT_TEST_FILE_LIST="$PWD/.local/redis-tests.txt" bash backend/test.sh
```

Run from the repository root with `.local/` already created. The integration
test records its Redis PID and terminates only that owned process. Fast router
and receiver regressions remain in the normal hermetic unit suite.
