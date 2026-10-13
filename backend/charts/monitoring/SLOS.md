# Journey SLOs (proposed, not deployed)

Read-only production measurement: **2026-10-03T06:10:00Z to 2026-10-13T06:10:00Z**.
These are event-weighted, rolling **10-day** objectives. Targets are provisional,
below corrected measured success, with headroom; they need operator acceptance.
They measure server delivery/completion boundaries, without client rendering proof.

| Journey | Target | Measured success | Good / valid events |
| --- | --- | --- | --- |
| live | 95.0% | 95.5055% | 167,954.37 / 175,858.41 |
| chat | 99.5% | 99.8470% | 8,056.33 / 8,068.68 |
| pusher | 95.5% | 96.0863% | 463,701.06 / 482,588.16 |

All selected valid counters were present at 241 hourly inventory samples.
`increase` is applied per instance before summing, so resets are handled and
fractional extrapolated counts are expected. Queries use Unix `1791871800`:

live:
```promql
sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome="transcribed"}[10d])) / sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[10d]))
```

chat:
```promql
sum(increase(omi_journey_terminal_total{job="cloud-run-application-metrics",journey="chat_response",outcome="success"}[10d])) / sum(increase(omi_journey_accepted_total{job="cloud-run-application-metrics",journey="chat_response"}[10d]))
```

pusher:
```promql
sum(increase(omi_journey_terminal_total{job="pusher-metrics",journey="pusher_session",outcome="success"}[10d])) / sum(increase(omi_journey_accepted_total{job="pusher-metrics",journey="pusher_session"}[10d]))
```

## Eligibility and failure semantics

Live now uses `omi_live_session_transcript_outcome_total`: GOOD is `transcribed`,
VALID is `transcribed|no_transcript`, BAD is `no_transcript`. This includes the
review's silent-provider failures closed normally (1000/1001), not just explicit
provider errors. STT terminal death/1011 counts even before ten seconds of audio.
Other sessions with >=10 seconds audio and speech but no delivered transcript
fail. Short/silent sockets, including silent 90-second idle reaps, are `too_short`
and excluded. Speech-bearing idle reaps without a transcript count as bad.
The rules use exactly the runtime's `_session_transcript_outcome` classification.

The prior 99.1904% client-terminal SLI excluded cancelled no-transcript sessions
and included silent idle failures, so it was not an eligible speech-session SLI.
The corrected 95.5055% is the **same population and query** as the
previous 95.50% speech-session rate. The small numerical difference is solely the
shifted measurement endpoint, with fractional extrapolation and changed traffic;
there is no remaining semantic gap. See `backend/routers/listen/runtime.py`.

Chat and pusher use accepted work as VALID, successful terminals as GOOD, and
`clamp_min(accepted - success, 0)` as BAD per alert window. Cancelled/abandoned
work and work with no terminal remain in the denominator. The counters cannot
distinguish legitimate user cancellation, so none is subtracted. Pusher success
is a WebSocket session completion, not transcript delivery; chat success is the
server's terminal done delivery. Accepted and terminal events can straddle window
boundaries: in-flight sessions are conservatively bad, and completions from an
older window can offset new failures. This aggregate approximation is not a
cohort deadline SLI. **Retain the existing chat/pusher critical and fail rules**;
there is no demotion/deletion recommendation for those four identities.
Pusher's corrected rate is much lower than the old 99.9685% because the old
terminal-only population hid cancellations and unmatched accepted sessions.

For live window W, bad share is no_transcript / eligible sessions. For chat/pusher,
it is clamp_min(accepted - success, 0) / accepted. Sparse bad/success series are
zero-filled only against an observed valid denominator. No traffic burns no
budget. Missing SLI series is **NoData**, never healthy OK. All seven rules use
Grafana `noDataState=NoData`, `execErrState=Error` and the existing Telegram receiver.
The live signal warning ORs `absent()` for the session family and independent
accepted-audio family, plus <1 session outcome with >20 audio accepts in 1h.
Both missing families therefore fire even when the scrape endpoint stays up;
the warning has a five-minute pending period. Quiet outcomes prove emission.

## Burn windows and volume

Burn is bad share / (1 - target). Each pair is AND; positive arms are ORed into
one critical and one warning identity per journey. No extra pending delay.

| Severity | Pair 1 | Pair 2 | live bad share | chat bad share | pusher bad share |
| --- | --- | --- | --- | --- | --- |
| critical | 1h AND 5m >14.4x | 6h AND 30m >6x | 72% / 30% | 7.2% / 3% | 64.8% / 27% |
| warning | 24h AND 2h >3x | 3d AND 6h >1x | 15% / 5% | 1.5% / 0.5% | 13.5% / 4.5% |

Each pair requires >=20 long-window and >=5 short-window valid events, except
chat's fast five-minute gate is **2**. Chat averages
2.80 accepts per five minutes; the old five-event gate exceeded measured volume.
A ten-minute total chat outage at that rate yields about
5.60 misses, >7.2% in the 1h window and 100% in the 5m window, so it pages.
Synthetic exact-expression Prometheus results for cancelled and no-terminal
chat/pusher outages are saved in the receipt and checked against current rules.
Pusher additionally pages when >=20 accepted sessions have zero successful completions
in ten minutes. This independent arm covers complete hangs at the lower target.
Contracts check **every journey/window gate** against its measured baseline rate.
These averages do not guarantee pages during lower-volume periods.

On a 10d budget, 1h at 14.4x consumes 6% and 6h at 6x consumes 15% under steady
traffic; warning pairs consume 30%. Full 3d windows fit within 10d retention,
but the oldest retained data cannot reconstruct full windows.

## Backtest, exclusions and rollout

| UID | Intervals all / post-warm-up | True samples | Evaluated / expected |
| --- | --- | --- | --- |
| `omi-slo-live-critical` | 0 / 0 | 0 | 2881 / 2881 |
| `omi-slo-live-warning` | 7 / 7 | 173 | 2881 / 2881 |
| `omi-slo-chat-critical` | 8 / 8 | 9 | 2881 / 2881 |
| `omi-slo-chat-warning` | 0 / 0 | 0 | 2881 / 2881 |
| `omi-slo-pusher-critical` | 0 / 0 | 0 | 2881 / 2881 |
| `omi-slo-pusher-warning` | 8 / 1 | 634 | 2881 / 2881 |
| `omi-slo-live-signal-dead` | 0 / 0 | 1 | 2881 / 2881 |

All changed rules were queried with 300s steps in sequential one-day chunks.
The receipt contains every sampled UTC interval and exact expression, with first
6h/3d/1h excluded for conservative critical/warning/liveness warm-up counts.
Five-minute sampling can miss shorter intervals. These counts are conditions,
not Grafana incidents or Telegram notifications. Gaps remain gaps, not healthy.
No causal claim follows from temporal overlap. The October 7 sync poll storm is
outside this SLI scope; no low burn result establishes sync or whole-product health.

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
