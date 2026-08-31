# Real-Traffic Journey Outcomes

`omi_journey_*` and `omi_live_stt_*` measure user-originated traffic only. They do not create test
accounts, synthetic canaries, or generated requests. Dev/beta and production
are intentionally isolated: each Prometheus instance evaluates only the
traffic it scrapes, with no cross-environment comparison or labels.

## Closed metric contract

| Metric | Labels | Meaning |
| --- | --- | --- |
| `omi_journey_accepted_total` | `journey` | A production boundary accepted work. |
| `omi_journey_terminal_total` | `journey`, `outcome` | A one-shot terminal outcome for accepted work. |
| `omi_journey_latency_seconds` | `journey`, `outcome` | Acceptance-to-terminal latency. |
| `omi_live_stt_accepted_total` | `provider`, `client_platform`, `deployment_environment` | A listener accepted its first nontrivial live-STT audio frame. |
| `omi_live_stt_terminal_total` | `provider`, `outcome`, `client_platform`, `deployment_environment`, `phase` | A one-shot terminal outcome for an accepted live-STT attempt. |
| `omi_live_stt_terminal_failures_total` | `provider`, `outcome`, `client_platform`, `deployment_environment`, `phase` | Provider failure detail correlated with a live-STT terminal. |
| `omi_capture_finalization_reconciliations_total` | `outcome` | A stale durable capture job was requeued, or its requeue handoff failed. |
| `omi_capture_finalization_failures_total` | `reason` | A persisted finalizer failed with one privacy-safe reason: `memory_fence`, `memory_config`, `provider`, `stale`, or `processing`. |
| `listen_finalization_oldest_nonterminal_age_seconds` | none | Age of the oldest queued, leased, or BYOK-blocked capture finalization job. |
| `listen_finalization_durable_jobs` | `state` | Authoritative Firestore job projection: `accepted`, `success`, `failure`, `stale`, `nonterminal`, `blocked_byok`, or `terminal_unknown`. |

`journey` is exactly `chat_response`, `pusher_session`, or
`capture_finalization`. Generic journey `outcome` is exactly `success`, `failure`,
`cancelled`, or `stale`; reconciliation `outcome` is exactly `requeued` or
`enqueue_failed`. Live-STT terminal `outcome` is exactly `success`, `failure`,
or `cancelled`; its terminal `phase` is exactly `transcript_delivery`,
`initialization`, `connection`, `send`, or `teardown`. `provider` and
`client_platform` use their existing closed vocabularies, and
`deployment_environment` is one of `prod`, `dev`, `local`, `offline`, or
`unknown`. There are no user, conversation, request, error-text, revision,
image, provider-model, or content labels.

## Client-segmented journey foundation

The existing `omi_journey_*` family above is intentionally unchanged. It is a
closed, alert-backed contract with historical `stale` semantics. New semantic
journeys use a separate family so adding client segmentation does not silently
rewrite that contract:

| Metric | Labels | Meaning |
| --- | --- | --- |
| `omi_client_journey_accepted_total` | `journey`, `client_kind` | A semantic journey was accepted. |
| `omi_client_journey_terminal_total` | `journey`, `client_kind`, `outcome` | Its one-shot coarse terminal result. |
| `omi_client_journey_issues_total` | `journey`, `client_kind`, `issue_class` | One bounded detail for a failed, degraded, or unknown terminal. |
| `omi_client_journey_duration_seconds` | `journey`, `outcome` | Acceptance-to-terminal duration. |

`outcome` is `success`, `failure`, `degraded`, `cancelled`, or the coercion
sentinel `unknown`. `degraded` means the request completed but did not deliver
the requested primary product result. `canned_fallback` and `quota_capped` stay
separate `issue_class` values; they must not be inferred from the coarse
outcome. Failure/degradation detail is a separate counter, and `client_kind` is
omitted from the histogram, to avoid multiplying every histogram bucket.

`client_kind` prefers the bounded `X-App-Platform` value, then recognizes only
known User-Agent families. Headerless CFNetwork and Electron clients resolve to
macOS and Windows respectively; headerless Dart resolves to
`dart_mobile_unknown_os`. Both pi-mono extensions currently send the same
`OpenAI/JS 6.26.0` User-Agent, so both resolve to `pi_mono_unknown_os`. The
server cannot separate them until the clients send `X-App-Platform`; it must not
guess an operating system.

The family is zero-initialized; only the wired journeys below emit real traffic,
and no client-segmented alerts exist yet. A zero is meaningful only with the
owning scrape job/revision selected; an unrelated healthy exporter also exposes
the bounded zero children. Its closed
cartesian product is capped at 3,915 Prometheus series per process with the
pinned client's `_created` series enabled: 180 accepted, 900 terminal, 1,980
issue, and 855 histogram series.

Streaming callers must pass their source through
`ClientJourneyAttempt.observe_stream` and provide both semantic predicates. A
`[DONE]` frame is only a success candidate; `failure_when` must recognize every
in-band error frame and assign its bounded `failure_class`. A detected error
terminalizes immediately and cannot be overwritten by a later `[DONE]` or clean
stream exhaustion. This is what detects failures emitted after HTTP 200 headers
have already been committed.

Desktop call sites use these boundaries:

- `desktop_chat` covers `/v2/chat/completions`, including its managed-gateway and
  direct-Anthropic branches. A stream succeeds only after at least one nonempty
  content/tool delta, a `[DONE]` frame, and clean exhaustion. A nonstreaming
  response succeeds only with nonempty assistant content or a tool call. In-band
  `error` frames, empty answers, provider errors, and incomplete streams are not
  successes.
- `desktop_proactivity` covers the strict `/v1/desktop/proactivity/completions`
  facade and generative calls through the legacy desktop Gemini proxy. The strict
  facade succeeds only after its requested JSON schema validates. A legacy Gemini
  stream needs nonempty candidate text plus a terminal `finishReason`; a normal
  response needs nonempty candidate text. Per-user Redis caps are `degraded` with
  `quota_capped`, while provider and invalid-response shapes are failures.

Client journey metric writes are fail-open. Collector or registry exceptions are
swallowed at the observability boundary and cannot change the product response.

Acceptance and terminal counters are event rates, not an in-flight gauge.
Never subtract them to infer backlog across processes or restarts. A journey
accepted in one process and completed in another must persist its acceptance
time for duration, export both sides to the same telemetry backend, and use a
durable lifecycle projection/queue gauge for outstanding work. Capture
finalization's `listen_finalization_durable_jobs` is the existing pattern.

The wired client-segmented boundaries are:

- `live_transcription`: accepted with the existing live-STT attempt after the
  first nontrivial audio frame; succeeds after the first nonempty transcript is
  sent, fails on a provider/live-session terminal, and otherwise cancels. The
  existing `omi_live_stt_*` contract remains authoritative and unchanged.
- `realtime_voice`: accepted after the voice-message WebSocket is admitted;
  succeeds after a nonempty transcript is sent, fails on provider setup/send or
  an empty finalized answer, and cancels on client disconnect.
- `conversation_finalization`: accepted only when the Firestore outbox creates
  a new job; succeeds only after durable finalization completes, fails when the
  job dead-letters, and cancels when lifecycle fencing makes the job stale. The
  existing `capture_finalization` journey remains unchanged.
- `app_webhook_delivery`: one attempt per eligible app or developer webhook;
  succeeds only on a 2xx response and fails on rejection, timeout, invalid
  target, circuit-open dependency, or transport/provider error. Enqueueing or
  scheduling a send is not success.

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
- Live STT is accepted when `/v4/listen` receives its first
  nontrivial audio frame. `success` is recorded only after the server has sent
  the first nonempty transcript payload to that WebSocket. This cannot prove
  the client rendered the payload. An upstream/live-session failure or an
  unexpected listen worker failure is `failure`; all other endings before a
  transcript send are `cancelled`. Provider failures preserve their bounded
  provider outcome and phase in `omi_live_stt_terminal_failures_total`; the
  matching accepted attempt has one `failure` terminal in
  `omi_live_stt_terminal_total`.
- `capture_finalization` is accepted only once, when the Firestore finalization
  outbox creates a new durable job. Successful completion is `success`, a
  dead-letter is `failure`, and a lifecycle-fenced durable job is `stale`.
  Existing job re-dispatches do not increment acceptance. Historical terminal
  rows without the bounded field are `terminal_unknown`; `blocked_byok` stays
  intentionally nonterminal. This Firestore projection is the capture
  denominator: PromQL takes `max` across listener pods, then uses
  `clamp_min(delta(...), 0)` for movement. It never sums replicated global
  gauges. A dead-emission condition is bounded new `accepted` movement with
  zero new `success`/`failure`/`stale` movement.

## Dashboard, alerts, and scrape health

The **Resilience / Fallbacks** dashboard retains the generic journey terminal
success rate for `chat_response`, `pusher_session`, and `capture_finalization`,
and adds a separate Live STT failure/accepted-attempt rate. The generic rate
intentionally uses only terminal `success` and `failure` outcomes: cancelled
client/transport endings and stale fenced capture jobs stay visible but do not
masquerade as application failures.

The terminal-success-rate panel stays empty (N/A) until a journey has a terminal
success-or-failure outcome; it never presents idle traffic as a 0% success rate.

The Live STT product-failure alert requires at least 20 accepted listener attempts in 30 minutes,
then alerts only when bounded live-STT failure terminals exceed 10% of those attempts for 10 minutes.
The other product-failure alerts require at least 20 terminal success-or-failure outcomes in 30 minutes,
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

Both Pusher release workflows verify the live Grafana provisioning contract
before any image publication or promotion. This requires the protected
`GRAFANA_TOKEN` secret and proves the exact memory-admission and capture-outcome
rule identities and expressions, unpaused state, healthy Prometheus datasource,
current healthy Pusher/backend-listen scrape targets, and Telegram contact-point
route. The post-rollout proof additionally requires all three finalization
metric families from both jobs; the pre-publish phase intentionally does not
require a metric family that the candidate introduces, avoiding bootstrap
deadlock. Missing credentials, an absent post-rollout family, or any live/source
mismatch blocks the release.

The live-transcription failure alert uses Grafana `noDataState: OK`: an empty
result is expected before that traffic exists and is not an outage.

## Page-class journey SLI alerts

The warning-class rules above report degradations; they did not page during
the 2026-08-30 capture-finalization outage, when `capture_finalization`
success sat at 0% for hours (failure ~360/h, stale ~290/h, accepted ~750/h)
while listen pods, WebSockets, LB traffic, and 5xx rates all stayed green.
These `severity: critical` rules page on the user outcome itself. All live in
the `Resilience` group and link the matching **Omi Core Features** panel.

| Rule | Fires when | Traffic gate | `noDataState` |
| --- | --- | --- | --- |
| `omi-journey-capture-success-critical` | capture success share < 0.90 for 10m | ≥ 20 accepted in 30m | `NoData` |
| `omi-journey-pusher-success-critical` | pusher success share < 0.90 for 10m | ≥ 20 accepted in 30m | `NoData` |
| `omi-journey-chat-success-critical` | chat success share < 0.90 for 10m | ≥ 20 accepted in 30m | `NoData` |
| `omi-journey-capture-settle-gap` | accepted − settled > 50 per 1h for 15m | ≥ 100 accepted in 1h | `NoData` |
| `omi-capture-oldest-nonterminal` | oldest nonterminal job age > 3600s for 15m | none (queue-age is traffic-independent) | `Alerting` |
| `omi-capture-dead-letter-surge` | dead letters > 50 per 1h for 15m | none (each is a lost capture) | `Alerting` |
| `omi-capture-finalization-memory-fence` | any `memory_fence` or `memory_config` failure in 5m | none (the first admitted-runtime violation is actionable) | `Alerting` |

The success-share numerator and denominator both read `omi_journey_terminal_total`
for the same `journey` from the same emitter, gated on `omi_journey_accepted_total`
for that journey, so quiet hours cannot page and a partial emitter outage cannot
fake a healthy ratio. A total terminal stall with real accepted traffic yields a
0 share through `clamp_min(..., 1)` and pages here too.

Calibration (initial, from the 2026-08-30 incident fingerprint and documented
measurements; replay against production history when the rules are imported):

- **0.90 paging floor** — the Core Features tiles display 95/99 thresholds; a
  sustained 90% floor with real traffic is unambiguous user harm. The incident
  sat at 0% for hours.
- **≥ 20 accepted / 30m** — the incident ran ~375 accepted per 30m; 20 is the
  same floor the existing warning rules use for terminal outcomes.
- **Gap > 50 / 1h at ≥ 100 accepted / 1h** — the incident left ~100 journeys
  per hour accepted-but-never-settled while the backlog aged to 5.9 days;
  normal in-flight work settles in minutes, so a 1h window gap stays near zero.
- **Oldest job > 3600s** — healthy finalization drains in minutes; the
  incident's oldest job was ~5.9 days old.
- **Dead letters > 50 / 1h** — the incident produced ~2.5k dead letters per
  day (~104/h); each dead letter is a capture that exhausted every retry.
- **Any memory admission failure** — a host that accepted persisted
  finalization work but cannot pass the canonical-memory fence violates its
  declared capability. Halt promotion, preserve the durable retry queue, and
  compare the serving image and PodTemplate receipt with the qualified release;
  do not log or inspect transcript content to diagnose it.
- **Chat liveness gate** (`omi-journey-signal-dead` chat arm) — the
  `omi:auto:chat-agent` lane measured min 9, p01 15, p05 23 requests/hour
  over 7 production days; `> 20/1h` demands liveness only at above-p05
  chat demand.

The two queue rules use `noDataState: Alerting` because their series are
unlabeled and zero-initialized: every scraped backend-listen replica exports
them at zero, so absence means the emitter or its scrape is gone, which is
itself page-worthy during real traffic.

Known blind spots: a server can only observe the SSE/WS boundary it controls,
not client rendering; process restarts may defer a terminal metric until the
durable worker/reconciler resumes; and a durable job still within its bounded
reconcile delay is deliberately nonterminal rather than an immediate failure.
