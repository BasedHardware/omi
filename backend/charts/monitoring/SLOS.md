# Journey SLOs (proposed, not deployed)

Read-only production measurement: **2026-10-03 05:10 to 2026-10-13 05:10 UTC**.
These are event-weighted success objectives over a rolling **10-day** period,
not latency or client-rendering guarantees. Targets sit below observed success,
with useful headroom; they are provisional until an operator accepts the scope.

| Journey key | Target | Measured success | Good / valid events (Prometheus increase, rounded) |
| --- | --- | --- | --- |
| live | 99.0% | 99.1904% | 173,195.19 / 174,608.80 |
| chat | 99.5% | 99.8384% | 8,048.97 / 8,062.00 |
| pusher | 99.9% | 99.9685% | 463,904.14 / 464,050.19 |

Each selected counter was present at all 241 hourly inventory samples. This
establishes ingestion, not continuous scrape coverage or perfect instrumentation.
`increase` handles per-instance resets before summing; fractional extrapolated
counts are expected. Baseline queries were evaluated at `1791868200`.

SLI: `sum(increase(GOOD[10d])) / sum(increase(VALID[10d]))`, with selectors below.
For any alert window W, bad share is
`(sum(increase(BAD[W])) or sum(increase(VALID[W])) * 0) / sum(increase(VALID[W]))`.
The zero-fill is conditional on a valid denominator: never invent traffic when
all series are absent. Cancellation is excluded; zero valid events do not burn.

| Key | VALID selector | GOOD outcome | BAD outcomes |
| --- | --- | --- | --- |
| live | `omi_client_journey_terminal_total{job="backend-listen-metrics",journey="live_transcription",outcome=~"success\|failure\|degraded\|unknown"}` | success | failure, degraded, unknown |
| chat | `omi_journey_terminal_total{job="cloud-run-application-metrics",journey="chat_response",outcome=~"success\|failure"}` | success | failure |
| pusher | `omi_journey_terminal_total{job="pusher-metrics",journey="pusher_session",outcome=~"success\|failure"}` | success | failure |

Replace the outcome filter with `outcome="success"` for GOOD and the BAD regex
for BAD. Live measures first nonempty transcript delivery, mobile chat measures
server terminal `done:` delivery, and pusher measures successful WebSocket close
without application failure. None proves client rendering. See
[boundary semantics](../../docs/runbooks/real-traffic-journeys.md).

Inventory exclusions and limitations:

- `omi_live_stt_terminal_total`: 160,373 successes / 162,766 success-or-failure
  terminals (~98.53%). Retain as provider/attempt diagnostic; the selected client
  boundary measures transcript delivery. `omi_listen_*`, provider-connect and
  stream-close counts lack a matching final user-outcome denominator.
- `omi_live_session_transcript_outcome_total`: 167,757 transcribed / 175,660 valid
  (~95.50%, excludes too_short). This stricter speech-session signal needs its
  own semantic/incident calibration; do not imply the selected 99% delivery SLO
  guarantees transcription for every speech-bearing session.
- Gateway: 28,773.74 success / 28,787.84 success-or-error chat-agent calls
  (~99.951%). `llm_gateway_requests_total` counts provider terminal completion,
  includes non-chat lanes and retries/fallbacks; it cannot replace a client SLI.
- Desktop chat: client journey counters show 27,593.52 success / 91,135.88 valid
  (~30.28%). A follow-up 10d issue query returned ~63,527 upstream_rejected
  events; that class includes HTTP 4xx, so this is not a proven 70% service
  outage or a valid-events SLI. Classify rejections before picking an objective.
  Do not pool desktop with mobile or choose a meaningless 30% target.
- **Sync/upload: withheld**. `omi_sync_transcription_job_total[10d]` returned only
  an upstream_error child with zero increase; the current instant query was
  empty. No successful job counter or upload terminal pair exists in the queried
  production inventory. `omi_sync_job_poll_requests_total` rose 44,637,427.46;
  polling/throttling is traffic, not completed upload/transcription. Sync phase
  histograms and Parakeet prerecorded outcomes measure substeps, not jobs.
- Capture finalization has success/failure/stale counters but is a separate
  journey with durable lifecycle projections; retain its existing pages.

Burn is bad share / (1 - target). Following the
[Google SRE multiwindow pattern](https://sre.google/workbook/alerting-on-slos/):

| Severity | Pair 1 (both required) | Pair 2 (both required) | live bad share | chat bad share | pusher bad share |
| --- | --- | --- | --- | --- | --- |
| critical | 1h AND 5m >14.4x | 6h AND 30m >6x | 14.4% / 6% | 7.2% / 3% | 1.44% / 0.6% |
| warning | 24h AND 2h >3x | 3d AND 6h >1x | 3% / 1% | 1.5% / 0.5% | 0.3% / 0.1% |

Pairs are ORed into **one critical identity per journey** and one warning identity.
Both pairs additionally require >=20 long-window and >=5 short-window valid
terminals. This deliberately suppresses isolated low-volume failures; it can
miss outages affecting fewer users. No extra pending delay (`for=0s`). Retention
allows 3d but cannot reconstruct full windows at the oldest retained samples.
The requested 14.4x/6x thresholds are retained: on a 10d budget, one hour at
14.4x consumes 6%, and six hours at 6x consumes 15% (not the 30d example's 2%/5%).
Warnings use 24h/3d, consuming 30% at 3x/1x respectively. Missing data is OK for
these outcome rules; retain separate scrape/signal health alerts. The added
`omi-slo-live-signal-dead` warning requires >20 accepted audio attempts but <1
terminal of any outcome in 1h for 5m. Including cancelled terminals prevents
quiet sessions from masquerading as dead instrumentation. Query execution
errors remain Error. All rules use the existing Telegram receiver; warning
severity alone does not prove quieter delivery without notification-policy review.

## Backtest and rollout

Backtest results and exclusions are in `slo-backtest.prod.json` and the PR body.
No existing rule, live gate, or production configuration is changed. Provisioning
must wait for review and an operator-owned deployment. Before demotion, verify
live UID/expression equality, healthy sources, and Telegram delivery. Keep scrape,
provider-budget/authentication, integrity, queue-age and capture-finalization
alerts: outcome SLOs do not replace those contracts.

## Conditional demotion list

After live SLO validation, demote `omi-journey-pusher-success-critical` and
`omi-journey-chat-success-critical` to warning; delete their duplicate warning
rules `omi-journey-pusher-fail` and `omi-journey-chat-fail` in favor of SLO warnings.
Consider deleting `omi-journey-live-transcription-fail` only after confirming its
provider-attempt scope is fully covered by the selected delivery boundary.
No existing rules are changed here.

`aew926uoh6o00c` (pusher LB 5xx) is only a demotion candidate after verifying that
pre-WebSocket admission errors are covered: the session SLO begins at accept,
so it cannot replace admission monitoring today. Gateway lane-failure and
zero-success pages cover non-chat consumers and pre-client boundaries; keep
them until they can be scoped by journey. This slice offers two definite page
identity demotions and up to three duplicate warnings removed, not a reduction
of the entire reported ~96-rule fleet. There is no measured cost saving;
inline rules add evaluations and no stored recording-rule series.

Incident correlation: October 3's live burn coincides with ~223.84 client
`provider_error` events in the six hours ending 15:50 UTC; provider terminals
show ~175.68 Soniox failures in that window (different populations, correlation
only). The [October 7 poll-storm runbook](../../docs/runbooks/request-storm-alerts.md)
records incident onset at 12:00 UTC; the selected delivery SLIs have no sampled
page in that interval. They therefore **do not detect the sync poll storm**.
Keep the dedicated edge-throttling and duplicate-upload policies until a real
sync/upload outcome SLI is ingested; low delivery burn is not whole-product health.

| Rule family | Critical intervals, all / after 6h warm-up | Warning intervals, all / after 3d warm-up |
| --- | --- | --- |
| Live delivery | 4 / 2 | 5 / 0 |
| Mobile chat | 0 / 0 | 0 / 0 |
| Pusher session | 0 / 0 | 0 / 0 |

The live counter-silence warning has zero firing intervals. Every query used
300s steps in sequential one-day chunks. Missing evaluation samples are retained
as gaps, never filled as healthy; notification timing and intervals shorter than
five minutes are unverified. Exact expressions and UTC endpoints are saved in
`slo-backtest.prod.json`. The PR body lists all sampled intervals and demotions.
