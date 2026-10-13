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

Burn is bad share / (1 - target). Each classic pair is AND; positive arms are
ORed into one critical and one warning identity per journey.

| Severity | Pair 1 | Pair 2 | live bad share | chat bad share | pusher bad share |
| --- | --- | --- | --- | --- | --- |
| critical | 1h AND 5m >14.4x | 6h AND 30m >6x | 72% / 30% | 7.2% / 3% | 64.8% / 27% |
| warning | 24h AND 2h >3x | 3d AND 6h >1x | 15% / 5% | 1.5% / 0.5% | 13.5% / 4.5% |

Live and pusher critical keep both short windows. Each of those pairs requires
>=20 long-window and >=5 short-window valid events. One miss at each short gate
stays under that pair's burn threshold: live 5m is 20% < 72%, live 30m is
20% < 30%, pusher 5m is 20% < 64.8%, and pusher 30m is 20% < 27%.

Chat critical does not use the 5-minute or 30-minute ratio arms. At 2.80
accepts per five minutes, one miss is a 50% bad share, and that arm paged on
isolated residual misses while the 99.5% objective and the warning stayed
healthy. The 30-minute gate of 5 crosses 3% on one miss. Chat critical pages
when any of these is true:

- 1h bad share > 7.2% (14.4x), at least 4 bad events, and at least 20 accepts
- 6h bad share > 3% (6x), at least 7 bad events, and at least 40 accepts
- 10m zero-completion: at least 5 accepts and fewer than 1 success

The pending period is 2 minutes, so one evaluation blip does not page. At
0.560 accepts per minute, four misses accumulate in about 7.1 minutes. The
1-hour arm then stays true until those misses age out, so a 10-minute total
outage (accepts continue, successes stay at 0) pages about 9.1 minutes after
it starts. The zero-completion condition is true for about 3.6 minutes around
the end of that outage, which is longer than the pending period, so that arm
pages at about 10.2 minutes as well. One to three misses in an hour fail the
4-event gate. One miss at the 20-accept floor is 5% < 7.2%. One miss at the
40-accept floor is 2.5% < 3%.

Warning rules keep the classic pairs, with >=20 long-window and >=5
short-window valid events. Pusher critical also pages when >=20 accepted
sessions have fewer than 1 success in ten minutes. Live critical has no
10-minute zero-completion arm. Each rule's `threshold` and `scope` name exactly
the windows in its expression. Synthetic exact-expression Prometheus results
for cancelled and no-terminal chat/pusher outages are in the receipt.
Contracts check every journey/window gate against its measured baseline rate,
that one miss at each critical volume gate stays under that arm's burn
threshold, and that chat critical receipt intervals stay within bound.
These averages do not guarantee pages during lower-volume periods.

On a 10d budget, 1h at 14.4x consumes 6% and 6h at 6x consumes 15% under steady
traffic; warning pairs consume 30%. Full 3d windows fit within 10d retention,
but the oldest retained data cannot reconstruct full windows.

## Backtest, exclusions and rollout

| UID | Intervals all / post-warm-up | True samples | Evaluated / expected |
| --- | --- | --- | --- |
| `omi-slo-live-critical` | 0 / 0 | 0 | 2881 / 2881 |
| `omi-slo-live-warning` | 7 / 7 | 173 | 2881 / 2881 |
| `omi-slo-chat-critical` | 0 / 0 | 2 | 2881 / 2881 |
| `omi-slo-chat-warning` | 0 / 0 | 0 | 2881 / 2881 |
| `omi-slo-pusher-critical` | 0 / 0 | 0 | 2881 / 2881 |
| `omi-slo-pusher-warning` | 8 / 1 | 634 | 2881 / 2881 |
| `omi-slo-live-signal-dead` | 0 / 0 | 1 | 2881 / 2881 |

Chat critical was re-queried on this same endpoint after its page was redesigned.
The condition was true on 2 samples, `2026-10-08T16:10:00Z` and
`2026-10-08T16:55:00Z`, 45 minutes apart. Neither sample has a true neighbor, so
the 2-minute pending period records 0 firing intervals. At 16:10Z the 1h window
had 4.02 bad events out of 33.2 accepts and the 6h window had 3.84 bad events,
under its gate of 7. At 16:55Z the 1h window had 5.32 bad events out of 55.4
accepts, while the 10m window had 3.99 accepts and 0 successes, below the
5-accept zero-completion floor; the next sample was healthy, which matches
in-flight turns completing. These are single-sample crossings, not a sustained
outage. Spot checks were instant queries of `clamp_min(accepted - success, 0)`,
accepted, and success at those two timestamps for the 1h, 6h, and 10m windows.

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
