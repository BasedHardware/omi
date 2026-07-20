# Real-Traffic Journey Outcomes

`omi_journey_*` measures user-originated traffic only. It does not create test
accounts, synthetic canaries, or generated requests. Dev/beta and production
are intentionally isolated: each Prometheus instance evaluates only the
traffic it scrapes, with no cross-environment comparison or labels.

## Closed metric contract

| Metric | Labels | Meaning |
| --- | --- | --- |
| `omi_journey_accepted_total` | `journey` | A production boundary accepted work. |
| `omi_journey_terminal_total` | `journey`, `outcome` | A one-shot terminal outcome for accepted work. |
| `omi_journey_latency_seconds` | `journey`, `outcome` | Acceptance-to-terminal latency. |
| `omi_capture_finalization_reconciliations_total` | `outcome` | A stale durable capture job was requeued, or its requeue handoff failed. |
| `listen_finalization_oldest_nonterminal_age_seconds` | none | Age of the oldest queued, leased, or BYOK-blocked capture finalization job. |

`journey` is exactly `chat_response`, `pusher_session`, `live_transcription`,
or `capture_finalization`. `outcome` is exactly `success`, `failure`,
`cancelled`, or `stale`; reconciliation `outcome` is exactly `requeued` or
`enqueue_failed`. There are no user, conversation, request, error-text,
provider, or content labels.

## Boundary semantics

- `chat_response` is accepted after `/v2/messages` has persisted the human
  message and prepared its SSE response. `success` is recorded when the server
  yields the terminal `done:` frame. `failure` means the server-side stream
  raised; `cancelled` means the stream ended before a terminal frame because
  its consumer disconnected or cancelled it. This cannot prove a client
  rendered the response after the server yielded it.
- `pusher_session` is accepted only after `/v1/trigger/listen` completes its
  WebSocket accept. Close codes `1000` and `1001` are `success` unless the
  server has already identified an application failure. A `1011` or stronger
  application failure is `failure`; other transport/client endings are
  `cancelled`, not product failures.
- `live_transcription` is accepted when `/v4/listen` receives its first
  nontrivial audio frame. `success` is recorded only after the server has sent
  the first nonempty transcript payload to that WebSocket. This cannot prove
  the client rendered the payload. An upstream/live-session failure or an
  unexpected listen worker failure is `failure`; all other endings before a
  transcript send are `cancelled`.
- `capture_finalization` is accepted only once, when the Firestore finalization
  outbox creates a new durable job. Successful completion is `success`, a
  dead-letter is `failure`, and a lifecycle-fenced durable job is `stale`.
  Existing job re-dispatches do not increment acceptance. A nonterminal job is
  reconciled after its bounded stale delay; use the reconciliation counter and
  oldest-nonterminal-age gauge to interpret accepted minus terminal work.

## Dashboard, alerts, and scrape health

The **Resilience / Fallbacks** dashboard includes all four journey success
rates and p95 latencies. Success rate intentionally uses only terminal
`success` and `failure` outcomes: cancelled client/transport endings and
stale fenced capture jobs stay visible but do not masquerade as application
failures.

The terminal-success-rate panel stays empty (N/A) until a journey has a terminal
success-or-failure outcome; it never presents idle traffic as a 0% success rate.

Product-failure alerts require at least 20 terminal success-or-failure outcomes in 30 minutes,
then alert only when the terminal failure share is above 10% for 10 minutes.
No traffic produces a zero accepted count and does not page. The separate
scrape-source alert requires both Prometheus jobs, `backend-listen-metrics` and
`pusher-metrics`, to be present and every target to be up; it distinguishes an absent metric source from a healthy,
idle product. Grafana query errors remain errors rather than product-outcome
alerts.

The expected authenticated `/metrics` scrape targets in both dev/beta and prod
are `backend-listen-metrics` (chat plus Cloud Tasks capture-finalization
worker) and `pusher-metrics` (pusher sessions plus inline capture finalization).
The metric children are initialized at process startup, so a scraped idle
target exports zeros; an absent series should be investigated as scrape or
deployment health, not read as zero traffic.

The live-transcription failure alert uses Grafana `noDataState: OK`: an empty
result is expected before that traffic exists and is not an outage.

Known blind spots: a server can only observe the SSE/WS boundary it controls,
not client rendering; process restarts may defer a terminal metric until the
durable worker/reconciler resumes; and a durable job still within its bounded
reconcile delay is deliberately nonterminal rather than an immediate failure.
