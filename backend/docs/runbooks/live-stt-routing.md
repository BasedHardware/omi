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
seen, otherwise censored. A provider death is counted without a speech minimum
when the serving owner replaces/rejects it or exhausts recovery. A pending hop
without successor text settles as degraded after 30 seconds, with no socket or
audio change. Established fallback reasons stay stable, including quota/auth;
health retains the corresponding typed account reasons. Soniox 408 uses censored `soniox_request_timeout`; 400 no-audio uses
`soniox_idle_timeout`. Neither opens a provider circuit for all users.

`omi_stt_cost_routing_settlements_total{target,outcome,reason,path}` is the
expected observation count from that seam (`path=close|failover|connect`). Its
sum over path must equal `omi_stt_cost_routing_observations_total` by
instance/target/outcome/reason. This comparison covers exactly the managed
router population; legacy/PTT fallback events are not extra router samples.
A direct acknowledgement from the observation writer feeds the single
`omi_stt_cost_routing_reconciliation_errors_total` counter; exceptions or missing
acknowledgements increment it. It proves emission, not persistence. Redis drop counters and
`omi_stt_cost_routing_votes_total{target,scope,result}` prove whether classified
evidence reached shared state (`applied|user_cap|window_full|generation|stage`).

State uses `omi:live-stt:cost-v6:<target>:<bounded-language>` and `all`. Do not
reuse v5 evidence. At stage 100, one hashed user contributes at most three
success/failure outcomes in a five-minute Redis-time window. Windows hold at
most 512 fingerprints and reject new identities on saturation rather than
restore old budgets by eviction. Raw observation counts remain uncapped for
reconciliation. Trials retain their separate user votes, generation fences,
5→25→100 shares, and exponentially increasing cooldown. Redis CAS enforces all
of this fleet-wide. Shared snapshots refresh off connect, normally every five
seconds, under a 75 ms deadline; local fallback retains known benches.

The [architecture](../../utils/stt/ARCHITECTURE.md#serving-owned-health-evidence-cost-v6)
has the taxonomy, registry and second-endpoint example, exact gate, and
reproducible calibration. The gate stays 8%. In cost-v6 simulation, every
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
2. Exactly zero reconciliation mismatch, evidence exceptions, unavailable
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
   static tail. Router-error fail-open still uses the documented static chain.
5. Transcript-success, no-text share, first-text latency, window capacity and
   GPU pressure remain within the conditions below. Confirm the existing
   transcript-success alert is evaluated and routed to the live contact point.

If low-volume coverage is missing after two hours, keep that target withdrawn
or remain shadow. This is a bounded first canary, not 24-hour reliability proof.
A new Modulate endpoint later enters through its own registry ID and 5% ramp;
its evidence must never reuse the old endpoint's identity or state.

## Exact PromQL

Use `job="backend-listen-metrics"`, and a window containing only the new image.
The **one-number reconciliation check** is the emission acknowledgement counter
below and must be zero. Missing metrics are failure of coverage, not zero.
The paired-counter difference is also useful by instance/target/reason, but a
scrape reads separate collectors at slightly different instants: a transient
difference during active settlement can be a scrape race. Require that the
one-minute minimum paired difference is zero, and investigate any persistent
mismatch; do not mistake `increase()` extrapolation or a first scrape for lost
evidence.

```promql
sum(omi_stt_cost_routing_reconciliation_errors_total{job="backend-listen-metrics"})
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
endpoint-specific equality is checked by the first query. For managed failure
settlements, account labels map budget→quota and rejected-auth→auth. Connect
settlements belong to `stt_selection`, terminal deaths to `stt_live_session`.

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

Abort to shadow/zero for any nonzero reconciliation or evidence exception; any
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
also restores static selection). Apply through the coordinator's config PR and
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
