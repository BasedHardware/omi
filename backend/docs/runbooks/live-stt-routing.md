# Live STT routing and Soniox runway

## Controls and rollout

`STT_ROUTING_MODE=off` keeps configured order. `shadow` computes cost-order
selection and bounded primary agreement without changing connections. `on`
applies it to `STT_ROUTING_ON_PERCENT` of UIDs, default zero. Production stays
shadow/zero on merge. Roll out on at 5 → 25 → 100%, using the headline transcript
SLI and first-text latency. Return to shadow/off or on-percent zero to restore
static selection. Keep Parakeet's independent allocation at its approved value.

The [cost router design](../../utils/stt/ARCHITECTURE.md#cost-ordered-health-gated-live-routing)
owns the registry schema, second-Modulate example, sequential statistical gate,
shared 5%/25%/100% recovery stages, false-positive/detection measurements and
limits. `STT_ROUTING_TARGETS_JSON` is the complete target registry override;
`STT_ROUTING_DISRUPTION_GATE` defaults to 0.08. The old
`STT_ROUTING_PROBE_PERCENT` control is retired. Expensive providers do not
receive artificial probe traffic. New endpoints reuse an existing provider
protocol; a genuinely new protocol first needs an adapter.

The connection path reads cached memory. Redis state is refreshed off connect
with a 75 ms deadline and eight bounded result-write slots. Redis faults retain
known benches and use local evidence; pods do not independently reopen cost
gate trials. Successful speech legs count at completion, failed/no-text legs
as soon as known. First-text `text`/`no_text` metrics remain diagnostic and are
not double-counted into the cost health test. The static-path legacy score and
account state remains available for local resilience; it does not rank the
active policy. Fleet deadlines use Redis server time; opposite +/-60-second
pod skews cannot start recovery early. During a Redis outage local evidence
keeps routing usable, and pending local benches reconcile before re-entry.

Window candidates must match the session's actual engine choice, language
eligibility and hosted endpoint. Mismatches and empty proposals restore the
configured chain and increment `omi_stt_cost_routing_fail_open_total`.
Configured unregistered services remain at the tail, followed by benched
targets as last resorts. Ordinary mid-session deaths exclude only the target;
quota/auth failures exclude its whole family.

The gate is a calibrated Page CUSUM, not an anytime-valid probability test.
At 3%/5%/7.5% baselines, 200 x 20k-session replays observe 0/1/24 false benches
per four million sessions. At 60% outage, median/p95 detection is 8/10 failed
sessions; 16% and 12% median detection is 264.5 and 972.5 sessions. A 10%
brownout has no prompt-bench SLA. Sparse languages can bench with two users,
sixteen recent failures and stronger score evidence; promotion at 30/60
passing sessions needs no distinct-user floor.

At 17.9k eligible sessions/day and 61% Modulate disruption, the delayed-result
trial replay averages 75.46 disruptions/day (p95 80; worst seeded run 83),
versus 545.95/day for an uninterrupted 5% trial. The deterministic replay bound
is below 100/day, including ten initial outage failures. This is conditional
on the documented workload/delay assumptions, not a hard production traffic
budget. Watch actual failovers and dropped writes before increasing the ramp.

## Read during rollout

Use the backend-listen Grafana dashboard and these PromQL queries:

```promql
sum by (provider, language, outcome) (rate(omi_stt_leg_transcript_outcome_total{job="backend-listen-metrics"}[15m]))
sum by (provider, outcome) (rate(omi_stt_provider_connect_total{job="backend-listen-metrics"}[15m]))
max by (provider, kind) (omi_stt_provider_circuit_open{job="backend-listen-metrics"})
histogram_quantile(0.95, sum by (le) (rate(omi_stt_routing_decision_seconds_bucket{job="backend-listen-metrics"}[10m])))
sum by (kind) (rate(omi_stt_fleet_health_write_dropped_total{job="backend-listen-metrics"}[5m]))
sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome="transcribed"}[5m])) / clamp_min(sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[5m])), 1)
```

Cost state uses `omi:live-stt:cost-v2:<target>:<bounded-language>` (and `all`)
with atomic compare-and-set updates and trial-start leases. A full result-write
pool, deadline or CAS contention can drop a fleet sample and increments
`omi_stt_fleet_health_write_dropped_total`; local evidence still advances.
Monitor dropped writes before increasing traffic. New dashboard panels should
show `omi_stt_cost_routing_decisions_total`, `omi_stt_cost_routing_shadow_total`,
`omi_stt_cost_routing_benched`, `omi_stt_cost_routing_stage`, and
`omi_stt_cost_routing_events_total`, and `omi_stt_cost_routing_fail_open_total`.
Transition logs include counts, failure rate and CUSUM score.
The bench/stage gauges show the last language queried per pod; use transition
logs to investigate language-specific health.

The `omi-modulate-failing-soniox` Telegram rule names the active spend lever.
The existing `Omi - Services Alerting (Telegram)` Grafana contact point must
reach David. The coordinator must verify this contact point and the live rule
evaluation after deployment; committed JSON alone is not delivery evidence.

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
