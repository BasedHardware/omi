# Live STT routing and Soniox runway

## Controls and rollout

`STT_ROUTING_MODE=off` keeps the configured provider order. `shadow` reads fleet
health and logs a sampled proposed order without changing the connection. `on`
orders only eligible providers by their rolling provider/language transcript
success score. The listen dev and prod manifests start at `shadow`. Promote
dev to `on` after observing the shadow decision rate and outcomes, then use a
small prod window before a wider rollout. Return to `shadow` or `off` through
runtime configuration if the headline session SLI or first-text latency moves
adversely. No image change is required for the kill switch.

The windowed Parakeet UID allocation and the non-English language arm retain
their selected first leg. Callback availability and language capability keep
unsupported providers out. An active account bench excludes a provider even
when it has the highest historical score. The deterministic probe floor
(`STT_ROUTING_PROBE_PERCENT`, 2 by default, maximum 10) tests eligible
lower-score providers. The score is three five-minute buckets of `text` and
`no_text` with a neutral prior; the event and metric labels have closed
provider/language/outcome vocabularies. Redis reads and writes have a 75 ms
default deadline (`STT_ROUTING_REDIS_TIMEOUT_SECONDS`, maximum 100 ms). A
Redis fault uses process-local scores and benches and never fails a session.

`STT_NO_TEXT_SECONDS=30` is the deadline from first VAD-confirmed speech to
first nonempty provider text. A leg with at least one second of confirmed
speech and no text at finish also counts `no_text`. The breaker opens on a
`no_text` leg in `on` mode; a later successful provider session can produce a
`transcribed` terminal outcome. The headline SLI still divides terminal
`transcribed` by `transcribed + no_transcript`, excludes `too_short`, and pages
below 90% for 10 minutes with at least 50 sessions in the five-minute window.
The dashboard shows 95% as the target, not a paging threshold.

## Read during rollout

Use the backend-listen Grafana dashboard and these PromQL queries:

```promql
sum by (provider, language, outcome) (rate(omi_stt_leg_transcript_outcome_total{job="backend-listen-metrics"}[15m]))
sum by (provider, outcome) (rate(omi_stt_provider_connect_total{job="backend-listen-metrics"}[15m]))
max by (provider, kind) (omi_stt_provider_circuit_open{job="backend-listen-metrics"})
sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome="transcribed"}[5m])) / clamp_min(sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[5m])), 1)
```

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
score, account/selection bench and recovery probe keys. The script refuses
more than 1,000 matching keys and uses short Redis socket deadlines. It does
not reset process-local circuits; those recover on their existing cooldown,
or after an operator controlled listen restart. Never point the script at a
different environment to clear a production alert.
