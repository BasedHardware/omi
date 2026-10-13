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

Pusher uses accepted work as VALID, successful terminals as GOOD, and
`clamp_min(accepted - success, 0)` as BAD per alert window. Cancelled/abandoned
work and work with no terminal remain in that denominator. Those counters cannot
distinguish legitimate user cancellation, so none is subtracted there. Pusher
success is a WebSocket session completion, not transcript delivery. Accepted and
terminal events can straddle window boundaries: in-flight sessions are
conservatively bad, and completions from an older window can offset new failures.
This aggregate approximation is not a cohort deadline SLI. **Retain the existing
chat/pusher critical and fail rules**; there is no demotion/deletion
recommendation for those four identities. Pusher's corrected rate is much lower
than the old 99.9685% because the old terminal-only population hid cancellations
and unmatched accepted sessions.

Both chat rules count bad events as explicit terminals
`outcome=~"failure|stale"`, divided by accepted work `clamp_min(..., 1)`.
`omi_journey_*` for chat is scraped from Cloud Run
(`job="cloud-run-application-metrics"`), and per-instance series churn makes
`sum(increase(accepted)) - sum(increase(success))` invent phantom misses. On
2026-10-08 the hours ending 16:00Z, 17:00Z, and 18:00Z had failure=0,
cancelled=0, and stale=0, while the hour ending 17:00Z had success 53.4545
against accepted 40.7150. `cancelled` stays out of the numerator because it
includes client disconnects. Chat success in the measured baseline is still the
server's terminal done delivery over accepts. A total chat outage (accepts with
no successes) is already paged by the live rules
`omi-journey-chat-success-critical` and `omi-journey-chat-fail` in
`alerts/resilience.json`, so chat critical has no 10-minute zero-completion arm.
Its pending period is five minutes. Chat warning keeps the classic pairs and
`for: 0s`; it uses the same explicit-failure numerator because a one-minute
replay of accepted minus success would have paged.

For live window W, bad share is no_transcript / eligible sessions. For pusher,
it is clamp_min(accepted - success, 0) / accepted. For chat, it is failure|stale
/ clamp_min(accepted, 1). Sparse bad series are zero-filled only against an
observed valid denominator. No traffic burns no budget. Missing SLI series is
**NoData**, never healthy OK. All seven rules use
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

Chat critical does not use the 5-minute or 30-minute ratio arms, and it does
not use a 10-minute zero-completion arm. At 2.80 accepts per five minutes, one
non-success is a 50% bad share, and that short arm paged on isolated residuals
while the 99.5% objective stayed healthy. The 30-minute gate of 5 crosses 3%
on one miss. A total outage remains on `omi-journey-chat-success-critical` and
`omi-journey-chat-fail`. Chat critical pages when either of these is true, with
bad events equal to `failure|stale` terminals and the denominator accepted:

- 1h bad share > 7.2% (14.4x), at least 4 bad events, and at least 20 accepts
- 6h bad share > 3% (6x), at least 7 bad events, and at least 40 accepts

The pending period is five minutes, so a one-minute counter blip does not page.
One to three explicit failures in an hour fail the 4-event gate. One failure at
the 20-accept floor is 5% < 7.2%. One failure at the 40-accept floor is
2.5% < 3%. Cancelled disconnects do not count as bad on this page.

Warning rules keep the classic pairs, with >=20 long-window and >=5
short-window valid events. Pusher critical also pages when >=20 accepted
sessions have fewer than 1 success in ten minutes. Live critical has no
10-minute zero-completion arm. Each rule's `threshold` and `scope` name exactly
the windows in its expression. Synthetic exact-expression Prometheus results
for cancelled and no-terminal chat/pusher outages are in the receipt. The chat
cases stay at 0 because a success gap is not an explicit failure or stale terminal.
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
| `omi-slo-chat-critical` | 0 / 0 | 0 | 2881 / 2881 |
| `omi-slo-chat-warning` | 0 / 0 | 0 | 2881 / 2881 |
| `omi-slo-pusher-critical` | 0 / 0 | 0 | 2881 / 2881 |
| `omi-slo-pusher-warning` | 8 / 1 | 634 | 2881 / 2881 |
| `omi-slo-live-signal-dead` | 0 / 0 | 1 | 2881 / 2881 |

Chat critical was re-queried on this same endpoint after the numerator changed
to explicit `failure|stale` terminals. The condition was true on 0 of 2881
samples, so the five-minute pending period records 0 firing intervals. The
previous accepted-minus-success expression had been true at
`2026-10-08T16:10:00Z` and `2026-10-08T16:55:00Z`. Those crossings were counter
artifacts: instant queries of the hours ending 16:00Z, 17:00Z, and 18:00Z on
2026-10-08 returned failure=0, cancelled=0, and stale=0. The hour ending 17:00Z
had success 53.4545 against accepted 40.7150. A 10-minute cancelled or
never-terminal gap, substituted into the exact expression and executed by
Prometheus, returns 0. Chat warning was re-queried on the same 300s grid after
it moved to the same numerator: 0 of 2881 samples.

### One-minute replay

Grafana evaluates every minute, so a 5-minute step under-samples a pending
period shorter than that step. `.agent-artifacts/slo1m.py` replayed the six burn
rules with `query_range` step 60s in ten one-day chunks, ending
`2026-10-13T11:04:42Z` under `ro-prod`. A run pages when
`last true sample - first true sample + 60s` exceeds `for`.

| UID | True minutes | Runs | Would page |
| --- | --- | --- | --- |
| `omi-slo-chat-critical` | 0 | 0 | 0 |
| `omi-slo-live-critical` | 0 | 0 | 0 |
| `omi-slo-pusher-critical` | 0 | 0 | 0 |
| `omi-slo-chat-warning` | 0 | 0 | 0 |
| `omi-slo-live-warning` | 869 | 10 | 10 |
| `omi-slo-pusher-warning` | 3777 | 18 | 18 |

The same script on the previous chat warning numerator (accepted minus success,
`for: 0s`) would have paged 11 single minutes on 2026-10-03 from 11:06Z through
14:02Z. Spot checks at the query_range sample for 11:06Z, 12:07Z, 12:29Z,
13:03Z, and 14:02Z showed failure=0, stale=0, and cancelled=0. The
accepted-minus-success gap was 1.03 to 1.33 events, which put the 6h and 3d
shares between 0.51% and 0.97%, above the 0.5% slow-burn threshold. The 24h
share stayed under 1.5%, so the fast pair did not fire. Explicit
`failure|stale` was 0, which is why the updated warning has no true minutes.

Live warning's 10 episodes are the slow pair only. At each episode start, the
6h and 3d `no_transcript` shares are above 5%, and the 2h and 24h shares are
below 15%. The 3d share is 5.002% to 5.199%, with 2,284 to 3,420
`no_transcript` sessions. That is the measured ~95.5% live rate sitting on the
95% target for a multi-day slice, not a one-event counter gap.

Pusher warning's 18 episodes are the slow pair only: 6h and 3d
accepted-minus-success share above 4.5%, while the 24h share stays under the
13.5% fast threshold. Explicit failure on the 3d window is 1.0 to 40.0;
cancelled is 5.0 to 748. Most of the gap is accepted work with no success
terminal. At `2026-10-06T03:31Z`, 6h bad is 702.5 of 14,103 accepts (4.98%),
of which failure is 3.0 and cancelled is 188.1, and the 3d bad share is 6.45%.
Pusher is not the Cloud Run chat counter, and this commit leaves that SLI in
place. Per-episode counts are in the receipt.

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
