# Journey SLOs (proposed, not deployed)

Read-only production measurement: **2026-10-03T11:40:00Z to 2026-10-13T11:40:00Z**
(`end_unix` 1791891600). These are event-weighted rolling objectives. Each
objective is set so the worst measured 3-day bad share uses about 70% of the
error budget: objective = round(1 - worst_3d / 0.70) to 0.1 percentage point.
Targets need operator acceptance. They measure server delivery/completion
boundaries, without client rendering proof.

| Journey | Target | 10d bad share | Worst 3d bad share | Worst 3d uses | Good / valid events |
| --- | --- | --- | --- | --- | --- |
| live | 92.1% | 4.5810% | 5.5098% at 2026-10-11T19:40Z | 69.7% of the 7.9% budget | 169,033.81 / 177,149.07 |
| chat | 99.4% | 0.1724% | 0.3987% at 2026-10-13T00:40Z | 66.4% of the 0.6% budget | 8,124.13 / 8,138.16 |
| pusher | 98.9% | 0.3479% | 0.7954% at 2026-10-07T11:40Z | 72.3% of the 1.1% budget | 464,689.66 / 466,311.73 |

Good events are valid minus bad under the alert SLI. `increase` is applied per
instance before summing, so resets are handled and fractional extrapolated
counts are expected. The 3-day figure is the maximum of 169 hourly evaluations
whose full window sits inside the 10-day retention.

live bad / eligible:
```promql
sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome="no_transcript"}[10d])) / sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[10d]))
```

chat bad / accepted:
```promql
sum(increase(omi_journey_terminal_total{job="cloud-run-application-metrics",journey="chat_response",outcome=~"failure|stale"}[10d])) / sum(increase(omi_journey_accepted_total{job="cloud-run-application-metrics",journey="chat_response"}[10d]))
```

pusher bad / terminal:
```promql
sum(increase(omi_journey_terminal_total{job="pusher-metrics",journey="pusher_session",outcome=~"failure|cancelled"}[10d])) / sum(increase(omi_journey_terminal_total{job="pusher-metrics",journey="pusher_session"}[10d]))
```

### Daily bad share, windows ending 11:40Z

| Ending | live | chat | pusher |
| --- | --- | --- | --- |
| 2026-10-04 | 3.5457% | 0.0000% | 0.1990% |
| 2026-10-05 | 3.3676% | 0.0000% | 0.1633% |
| 2026-10-06 | 5.2656% | 0.1184% | 0.9043% |
| 2026-10-07 | 4.3881% | 0.0000% | 1.1280% |
| 2026-10-08 | 4.5945% | 0.0000% | 0.2523% |
| 2026-10-09 | 5.1840% | 0.0000% | 0.0188% |
| 2026-10-10 | 5.5386% | 0.5729% | 0.1492% |
| 2026-10-11 | 4.7529% | 0.0000% | 0.0291% |
| 2026-10-12 | 3.7651% | 0.2533% | 0.0414% |
| 2026-10-13 | 4.6217% | 0.6745% | 0.0238% |

## Eligibility and failure semantics

Live uses `omi_live_session_transcript_outcome_total`: GOOD is `transcribed`,
VALID is `transcribed|no_transcript`, BAD is `no_transcript`. This includes
silent-provider failures closed normally (1000/1001). STT terminal death/1011
counts even before ten seconds of audio. Other sessions with >=10 seconds of
audio and speech but no delivered transcript fail. Short/silent sockets,
including silent 90-second idle reaps, are `too_short` and excluded.
Speech-bearing idle reaps without a transcript count as bad. The rules use the
runtime's `_session_transcript_outcome` classification.

Chat bad events are explicit terminals `outcome=~"failure|stale"`, divided by
accepted work `clamp_min(..., 1)`. `cancelled` stays out of the numerator
because it includes client disconnects. Over these 10 days chat `failure` was
14.03, `stale` was 0, and `cancelled` was 0. `omi_journey_*` for chat is
scraped from Cloud Run (`job="cloud-run-application-metrics"`). Per-instance
series churn makes `sum(increase(accepted)) - sum(increase(success))` invent
phantom misses, so chat does not use that subtraction. A total chat outage
(accepts with no successes) is already paged by
`omi-journey-chat-success-critical` and `omi-journey-chat-fail` in
`alerts/resilience.json`. Chat critical has no 10-minute zero-completion arm.
Its pending period is five minutes.

Pusher bad events are `omi_journey_terminal_total{journey="pusher_session",outcome=~"failure|cancelled"}`.
The denominator is every terminal outcome for that journey, not accepted work.
`pusher_session_outcome` in `backend/utils/pusher_protocol.py` returns
`failure` for `application_failed` or close 1011 (server-side abnormal close),
`success` for normal closes 1000 and 1001, and `cancelled` for every other
close. Success is excluded from the bad count. The registered `stale` label
increased by 0 over these 10 days, so it does not move the sum. In-flight
sessions have no terminal and cannot count. Over 10 days the terminal split was
success 464,689.66, failure 145.04, cancelled 1,477.03. Accepted work was
482,805.49; the gap to terminals is in-flight and window-edge sessions, which
this SLI leaves out. Hangs and total pusher outages stay on the existing
`omi-journey-pusher-success-critical` and `omi-journey-pusher-fail` rules.
There is no demotion or deletion recommendation for those identities, or for
the chat pair.

For live window W, bad share is no_transcript / eligible sessions. For chat, it
is failure|stale / clamp_min(accepted, 1). For pusher, it is failure|cancelled
/ all terminal outcomes. Sparse bad series are zero-filled only against an
observed valid denominator. No traffic burns no budget. Missing SLI series is
**NoData**, never healthy OK. All seven rules use Grafana `noDataState=NoData`,
`execErrState=Error` and the existing Telegram receiver. The live signal
warning ORs `absent()` for the session family and independent accepted-audio
family, plus <1 session outcome with >20 audio accepts in 1h. Quiet outcomes
prove emission.

## Burn windows and volume

Burn is bad share / (1 - target). The multipliers are unchanged: critical
14.4x and 6x, warning 3x and 1x. Each classic pair is AND; positive arms are
ORed into one critical and one warning identity per journey.

| Severity | Pair 1 | Pair 2 | live bad share | chat bad share | pusher bad share |
| --- | --- | --- | --- | --- | --- |
| critical | 1h AND 5m >14.4x | 6h AND 30m >6x | 113.76% / 47.4% | 8.64% / 3.6% | 15.84% / 6.6% |
| warning | 24h AND 2h >3x | 3d AND 6h >1x | 23.7% / 7.9% | 1.8% / 0.6% | 3.3% / 1.1% |

Live's 14.4x arm requires a bad share above 100%, so that pair cannot fire.
The 6h and 30m pair at 47.4% is the live page. Chat critical does not use 5m
or 30m ratios; its two numbers are the 1h and 6h thresholds.

Live critical keeps both short windows, with >=20 long-window and >=5
short-window eligible sessions. One miss at each of those gates stays under
that pair's burn share: 5m is 20% < 113.76%, and 30m is 20% < 47.4%.

Pusher critical uses the same pairs on terminal counts. One miss at the old
floor of 5 is a 20% bad share, which is above both 15.84% and 6.6%. The short
floors are therefore >=7 terminals in 5m (one miss is 14.29% < 15.84%) and
>=16 terminals in 30m (one miss is 6.25% < 6.6%). Long floors stay at 20.
Pusher critical has no 10-minute zero-completion arm.

Chat critical pages when either of these is true, with bad events equal to
`failure|stale` terminals and the denominator accepted:

- 1h bad share > 8.64% (14.4x), at least 4 bad events, and at least 20 accepts
- 6h bad share > 3.6% (6x), at least 7 bad events, and at least 40 accepts

The pending period is five minutes. One to three explicit failures in an hour
fail the 4-event gate. One failure at the 20-accept floor is 5% < 8.64%. One
failure at the 40-accept floor is 2.5% < 3.6%.

Warning rules keep >=20 long-window and >=5 short-window valid events. Each
rule's `threshold` and `scope` name exactly the windows in its expression.
Contracts check every journey/window gate against its measured baseline rate,
that one miss at each critical volume gate stays under that arm's burn
threshold, and that pusher expressions do not subtract accepts from successes.

On a 10d budget, 1h at 14.4x consumes 6% and 6h at 6x consumes 15% under steady
traffic; warning pairs consume 30%. Full 3d windows fit within 10d retention,
but the oldest retained data cannot reconstruct full windows.

## Backtest, exclusions and rollout

Five-minute `query_range` counts and the one-minute replay are in
`slo-backtest.prod.json` (`one_minute_replay`). Grafana evaluates every minute.
A run pages when `last true sample - first true sample + 60s` exceeds `for`.
The page target is 0 critical episodes and at most one warning episode per
rule across the 10 days.

**Sync/upload: withheld**. The original inventory had no ingested successful job
counter paired with a terminal denominator; millions of polls are not completed
uploads. Desktop chat's rejection-heavy counter needs eligibility classification;
do not pool it with mobile. Provider attempts and gateway completions measure
other boundaries and retain their diagnostic pages. Capture finalization remains
its own durable lifecycle journey.

No existing rules, live gate, deployment or production configuration changed.
Keep `omi-journey-chat-success-critical`, `omi-journey-pusher-success-critical`,
`omi-journey-chat-fail` and `omi-journey-pusher-fail`. Also keep pre-accept LB,
scrape/signal, gateway non-chat, provider budget/auth, integrity, queue age and
capture-finalization pages. Any future retirement requires cohort/hang coverage,
healthy source validation, exact live expression equality and Telegram proof.
This change closes blind spots; it claims no immediate page-count or cost saving.
Inline expressions add evaluation work without stored recording-rule series.
