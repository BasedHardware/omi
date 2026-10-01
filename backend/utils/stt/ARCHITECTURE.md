# STT utility architecture

This package owns backend-side speech-provider selection, socket resilience,
transcript normalization, VAD gating, and speaker-embedding policy. HTTP and
WebSocket orchestration lives in `backend/routers/`; the independently deployed
Parakeet runtime lives in `backend/parakeet/`.

## Live path

```text
routers/listen/receiver.py
  -> streaming.py                 provider sockets and fallback selection
  -> vad_gate.py                  optional audio admission/remapping
  -> speaker_identity.py          provider epoch and conversation-local IDs
  -> routers/listen/transcripts.py
  -> routers/listen/speakers.py   enrolled voiceprint matching
```

Provider fallback is a connection-time and serialized mid-session decision.
The legacy connection chain remains the default. `live_rollout.py` gates the new
configured chain (`live_chain.py`) and UID allocation; `live_session.py` owns its
VAD, audio timeline, usage ledger and fresh provider callbacks. `parakeet_window.py`
subclasses the existing batch adapter with bounded admission, sentence-anchored
growing POSTs (`window_anchor.py`) and teardown. Bounded peak AGC (0.8 of
full scale, 4× cap) scores a gained copy at ingest for VAD and applies one
uniform scale per POST from the original-level buffer. Fixed 6 s slices that start
mid-utterance make TDT return empty; each POST is `[anchor, now]`, completed
sentences are emitted, and the next POST starts at that sentence boundary.
VAD `finalize()` is a soft pause POST (emit the last sentence only when it
already ends with `.?!`); a 2 s wall-clock idle timer, not the hangover, is
what force-flushes held speech when the gate is dropping silence. Max-context
is not a force flush: two-plus segments re-anchor at the last emitted
sentence, a single run-on emits at that segment end, and an empty cap slides
one pace. The PCM buffer is two max-context windows plus two pace intervals
(60 s / ~1.9 MB at defaults) so a catch-up burst cannot shed a healthy
session.
`live_metrics.py` exposes bounded process/session metrics. Dead providers are excluded
from that session; each adopted provider gets a new speaker-provider epoch.
Operational controls and capacity arithmetic: [windowed live STT](../../docs/operational/windowed-live-stt.md).

## Language constraint

`language_policy.py` builds one immutable live-session profile from the client's
primary language and the account's single-language setting. Multilingual
non-English sessions expect the primary plus English. A stable UID hash can
prefer Soniox ahead of the normal configured chain; the percentage defaults
to zero in production. The profile and arm survive mid-session failover.
Multichannel, custom STT, and BYOK sessions stay outside routing and hints;
an explicit client Parakeet preference retains its existing priority.
`STT_MULTI_LANGUAGE_HINTS=false` restores Soniox's former unhinted `multi`
request. Soniox always keeps language identification enabled. Other providers
retain their existing language parameters and order.

When `STT_LEARNED_LANGUAGE_PROFILE=true`, a 20-session rolling projection on
`users/{uid}` supplies a spoken-language prior after three classified sessions.
The declared non-English primary keeps priority; languages with at least 20%
of classified segments and English with at least 10% enter a three-language
Soniox-validated set. An English-primary account can then enter the same
non-English Soniox-first UID arm. A failed or slow profile read uses the declared
prior. Session close schedules one bounded transaction off the listen loop;
the projection contains normalized language codes and counts only. Single
language, multichannel, custom STT and BYOK sessions do not read or write it.
The flag defaults off and is enabled only in development.

Soniox documents a `language` code on every token when identification is on;
its adapter uses final tokens only and passes a code only when all tokens in
one segment agree. Velma's live adapter reads an optional `language` on final
utterance frames (the batch response has per-utterance codes); live frame
presence has not been verified against a provider connection. When no provider
code is available, `langdetect` runs off the listen loop. At least 24 letters
avoid short-phrase guesses, and a 0.95 top-probability floor avoids calling
close-language guesses a mismatch. A 32-task per-session cap makes overflow
undetermined; each detector sees at most 512 characters to bound CPU time.
A local 200-call warm benchmark measured 1.2 ms median and
1.36 ms p95, with a 125 ms cold maximum, which is why detection runs off-loop.
Only normalized codes and bounded conformance labels reach metrics and logs;
the private provider-language field is removed before transcript persistence.

## Speaker boundaries

`speaker_embedding.py` owns enrolled voiceprint extraction; `speaker_match.py`
owns verification threshold and margin. They are not clustering controls. `speaker_clustering.py` owns the more
permissive short-clip clustering threshold and the eight-centroid cap used by
backend Parakeet paths. Once full, clustering merges a miss into the nearest
centroid and keeps the transcript: the forced merge is reported through the
shared fallback telemetry (`reason=capacity_full`) in backend paths — the
Parakeet image logs it — and the miss is kept out of the centroid's running
mean so a capped speaker cannot drag another speaker's centroid away.

`speaker_identity.py` scopes provider labels before persistence. It maps
`(speaker_id_scope, speaker)` to a small conversation-local integer after
hydrating IDs already stored on the conversation, so reconnects and provider
changes cannot reuse another numbering space. The cost is that one voice gets a
new id per scope; `conversation_speakers.py` (pure) re-diarizes the finished
conversation from per-segment embeddings so each id is one voice again, and
`utils/conversations/speaker_resolution.py` runs it before processing.
`voiceprints.py` owns which stored person embeddings are trusted.

## Other modules

- `pre_recorded.py` normalizes batch-provider output and uses the shared
  clustering policy when Parakeet has no server-side labels.
- `provider_resilience.py`, `safe_socket.py`, `socket.py`, and
  `live_failure.py` own provider health and terminal socket contracts.
- `routers/speech_profile.py` owns owner enrollment. `utils/speaker_identification.py`
  teaches other people from explicitly labeled speech; `database/users.py` atomically
  publishes sample, embedding and source identity and fences correction/deletion.
  These profiles do not assign in-session cluster identities. See the
  [teaching contract](../../../docs/doc/developer/backend/transcription.mdx).
- `vad.py` and `vad_gate.py` own speech admission; `outcomes.py` owns bounded
  transcription failure values.

The Parakeet image cannot import this package through an undeclared deployment
boundary, so `backend/parakeet/speaker_math.py` mirrors the two clustering
defaults and bounded-nearest policy for that image. Tests pin both copies.

## Why the chain looks like this (incident history)

These notes used to live on `streaming.py` helpers. They were moved here so
that file can stay under the line ratchet; the functions keep one-line
pointers back to this section.

`connect_stt_socket_with_fallback` connects the selected primary before audio
starts, walking the configured fallbacks. `STT_SERVICE_MODELS` states an ordered
preference, so a primary that cannot open a socket must advance to the next
configured provider instead of failing the session — a Deepgram account
rejecting every connect with HTTP 402 otherwise takes the whole deployment's
live transcription down (#11695). The chain must not stop at Modulate either:
with Deepgram at HTTP 402 and Modulate answering 500/over quota, an English
session died while a healthy Parakeet deployment sat idle behind them in the
same list (#11752). Modulate is a primary as well as a fallback: a deployment
listing `modulate-velma-2,dg-nova-3,parakeet` lost 100% of its sessions for
~50 minutes because a Modulate primary bypassed this helper entirely (#11752).
The circuit is deliberately process-local and never owns capacity. The Parakeet
service rejects excess streams at its GPU boundary; this helper only avoids
repeated connection latency while a provider is unhealthy.

A provider is never offered its own failure as a fallback, so the legacy chain
excludes the primary: a Modulate primary walks Deepgram then Parakeet (#11752).
The relative order of those fallback legs is fixed in the dark path and is not
parsed out of `STT_SERVICE_MODELS`; it matches the declared deployment config,
and callers already gate each leg on whether the deployment can serve it.
Reading the true order off the policy list is the ramped configured chain.

`_primary_streaming_service` returns the STT service leading
`STT_SERVICE_MODELS` for streaming. It walks the same policy-owned preference
list `get_stt_service_for_language` selects from, so a provider migration
(e.g. Deepgram → Modulate) that reorders that list is honored automatically
instead of leaving a call site naming a provider that stopped being primary.

`is_stt_available` is a best-effort, process-local signal for a client
pre-flight check. It reuses the existing per-process circuit breaker (a
latency optimization, not a fleet-wide coordinator — see
`provider_resilience.py`) for whichever provider is currently configured as
the streaming primary, rather than a provider hardcoded at the call site:
false only while that provider's breaker is open and its cooldown hasn't
elapsed yet after repeated recent failures. It uses `cooldown_elapsed()`
rather than raw `state` because the open→half_open transition otherwise only
happens inside `allow_request()` — without this, a quiet process with no
concurrent listen traffic would stay reporting "unavailable" forever after
the provider actually recovered. When the configured chain is enabled the
preflight returns true and leaves admission, including its bounded last-resort
probe, to the chain.

`parakeet_is_configured_fallback` is the same contract as
`modulate_is_configured_fallback`, one provider further down the ordered
`STT_SERVICE_MODELS` preference: the deployment must list Parakeet, the
policy must serve it, its endpoint must be configured, and it must support
the session's resolved provider language.

`get_stt_service_for_language` selects a serving STT provider allowed for the
requested product surface. `exclude` holds provider tokens that already died
for this session, so a mid-session failover asks for the next provider down
the chain rather than reselecting the one that just failed. A `dg-*`
configuration serves from whichever Deepgram deployment the runtime is
configured for — self-hosted when its endpoint is set, otherwise the hosted
API. Without credentials it falls through to the policy-owned alternatives
rather than failing the session. Only managed listen callers supply
`window_uid`; all other surfaces retain their legacy model policy, with
`parakeet-window` stripped from the configured list rather than replaced by
code defaults. Deepgram availability includes its runtime endpoint.

## Cost-ordered, health-gated live routing

`config/live_stt_registry.py` owns the target schema and default registry;
`live_router.py` filters capabilities, sorts by audio-hour cost (stable config
order for ties), then skips ramp exclusions, capacity signals and fleet benches.
The first surviving target is primary and the rest retain cost order for
failover. Capability checks include every expected language from the immutable
declared/learned session profile, so a declared English account with a learned
Hindi prior cannot enter an English-only target. Healthy cheaper targets take every eligible session within their
configured ramp and capacity. There is no portfolio split or worst-provider
probe. The existing Parakeet admission and batch-pressure gates still reject
at connect and overflow into the next target. Target IDs are distinct from
provider families: two Modulate endpoints have separate health and connection
breakers. A narrow typed-death hook routes a custom endpoint's serving failure
to its own local breaker, preserving the old endpoint's serving capacity;
account failures still quarantine their shared credential family.
`live_target_connect.py` reuses the existing Modulate socket protocol
for endpoint overrides; it does not change provider clients.

The registry defaults to `parakeet-window` ($0.02/audio-hour),
`modulate-velma-2` ($0.055), and `soniox` ($0.0754). These are routing estimates,
not billing measurements. `STT_ROUTING_TARGETS_JSON` replaces the entire list
(maximum 16 entries). Fields are `id`, `family`, `cost_per_audio_hour`,
`ramp_percent` (default 100), `languages` (optional restriction), `features`
(default `["streaming"]`), `endpoint` (optional Modulate WSS URL without query
parameters), and `capacity_env` (optional boolean environment signal). IDs must
be stable lowercase tokens of at most 48 characters. Family capabilities reuse
`stt_provider_policy`; configuration may restrict them, never expand them.
Callbacks and credentials must already be available on the managed chain.
A new wire protocol needs an adapter before it can become a config-only target;
this router does not re-enable Deepgram or invent provider SDKs.

`parakeet-window` always reads `PARAKEET_WINDOW_ALLOCATION_PERCENT`, including
its existing `sha256("parakeet-window:" + uid)` cohort. Its registry percentage
cannot override that safety control. Other target ramps use the same hash shape
with their target ID. Recovery uses a separate, nested sticky cohort, so a 5%
re-entry means 5% of sessions eligible under the configured ramp.

### Health evidence and hysteresis

`live_gate.py` implements a sequential mixture likelihood test, with three
alternatives above `STT_ROUTING_DISRUPTION_GATE` (default 0.08). Each session
invests 1/1024 of the evidence budget in a new possible change point, while
existing investments continue accumulating likelihood. This detects an abrupt
outage after a long healthy history without treating minutes as samples. The
mixture is an anytime-valid test within each 1024-session evidence block;
bench at likelihood evidence >= 1000 with at least eight speech sessions.
Fleet writes additionally require four distinct authenticated UID fingerprints
among the last eight failure outcomes. This prevents one caller from supplying
an entire outage, including after healthy traffic. Recovery promotion requires
four distinct sampled UIDs; session counts remain the statistical denominator.
The state retains at most four sample fingerprints and eight recent-failure
fingerprints (salted SHA-256 prefixes), never raw UIDs or user content. These
values are never metric labels or logs. Sparse cohorts may not meet the
diversity floor; local breakers still protect their connections.
Under independent Bernoulli outcomes with a rate at or below the gate, the
sequential false-bench bound is 0.1% per block/test (0.2% for the target and one language
test combined). Repeated blocks/languages increase that bound; it is not a
lifetime guarantee; fixed-sample trial rejection has its own false-rejection
probability. Changing the disruption gate resets the evidence generation
without clearing an existing bench. Synthetic tests observe zero benches over 200 seeded runs
of 5000 sessions at 3% (one million outcomes). The 95% upper bound for a
5000-session run's false-bench probability from those zero observations is
about 1.5%, rather than proof that false positives cannot occur.

A leg contributes once after at least one second of VAD-confirmed speech:
no text by the existing deadline, death/failover after text, or successful
completion. A known no-text or dead leg contributes immediately; successful
legs wait until close so later failure cannot be hidden by first text.
Intentional teardown does not count as a death. A healthy client close before
the first-text deadline is censored if no text arrives during drain; legacy
no-text diagnostics are preserved, but this is not provider failure evidence.
Actual text during drain still counts as successful completion. Legacy first-text counters
remain diagnostic and are not added to the session denominator. Target-global
and bounded-language evidence run independently; a language bench can restrict
that language, and sparse healthy languages inherit target-global health.
The language view is used after 30 samples or a decisive failure test.

Cold hard outages bench after eight failed speech sessions. The deterministic
warm-history tests bound detection to 15 failures, including a 12-failure
case crossing an evidence-block reset. The synthetic replay detects a hard
outage after seven additional failures and a 25% brownout after 64 speech
sessions. At 62 speech sessions/5 minutes, eight failures take approximately
39 seconds if all traffic serves that target, or 155 seconds at a 25% share,
plus outcome and cache delay. Long open successful sessions, sparse traffic,
local breaker cooldowns, dropped Redis writes and smaller cohorts make wall
clock detection slower. The statistical guarantee assumes independent
outcomes; repeated sessions from one UID can be correlated.

A bench waits 300 seconds initially. A failed trial doubles the wait, capped
at four hours. A fleet lease starts the shared 5% trial after cooldown when
this target would be cheaper than a surviving primary for some eligible
session. Thirty speech sessions spanning four sampled UIDs with disruption <= the gate promote to 25%;
sixty more promote to 100%. Trial failures from enough distinct callers trigger an early sequential bench,
or re-bench at the fixed sample boundary when the empirical rate exceeds the
gate. These are fixed-sample acceptance checks, not a high-confidence proof of
an 8% upper bound. Strike history clears after a full healthy evidence block.
A more expensive bench receives no primary probes while a cheaper target
serves it; it can remain unknown until needed. No pod starts a private trial
when Redis is down. Trial evidence is accepted only for the sticky re-entry cohort intersected
with the target ramp, including when existing static/shadow traffic supplies
observations. Out-of-cohort completions cannot accelerate a stage.
Outcomes carry a stage generation: completions from a
previous stage cannot promote a newer one.

`live_cost_health.py` stores target/global and target/language state in the
`omi:live-stt:cost-v1` Redis namespace. Compare-and-set updates preserve shared
counts and transitions across pods; leases serialize trial starts. A background
refresh uses the existing 75 ms deadline. Connect reads memory only. Redis
faults use local evidence and retain known benches, then unknown health and
configured cost order. A router exception restores today's configured chain. Local benches created
during Redis faults remain restrictive when Redis returns, and are reconciled
through CAS before staged recovery; snapshot and generation capture use the
same freshness/backoff predicate.
Account/billing refusals remain immediate protection; local connection/serve
breakers remain fast protection and cannot bypass an active fleet cost bench,
including the old last-resort path. Legacy provider-score state is retained for
static-path protection/telemetry, but never ranks the active cost router.
Registry field types and endpoint URL structure are validated before selection.
Initial same-family target overflow emits the shared fallback telemetry; a
normal cost-selected primary is not reported as a fallback. Existing
same-provider reconnects retain their selected target identity for health.
The managed mid-session receiver still records failed provider families, so a
serving death excludes all endpoints of that family for the remaining capture.
Changing that receiver algorithm is outside this PR and belongs to the separate
mid-session lane; initial connection attempts use target-scoped exclusions.

### Adding a second Modulate endpoint and rollout

Keep the current family enabled in `STT_SERVICE_MODELS`, its credential in
`MODULATE_API_KEY`, and supply this complete registry through
`STT_ROUTING_TARGETS_JSON` in the listen runtime overlay and matching chart:

```json
[
  {"id":"parakeet-window","family":"parakeet","cost_per_audio_hour":0.02},
  {"id":"modulate-next","family":"modulate","cost_per_audio_hour":0.05,
   "ramp_percent":5,"endpoint":"wss://new-modulate.example/stream"},
  {"id":"modulate-velma-2","family":"modulate","cost_per_audio_hour":0.055},
  {"id":"soniox","family":"soniox","cost_per_audio_hour":0.0754}
]
```

Replace the example URL and estimated cost with the endpoint being tested.
Ramp `modulate-next` 5 → 25 → 50 → 100 by changing only its `ramp_percent`.
The sample's lower cost places it ahead of the old Modulate endpoint; an equal
cost also does so because it appears first. A more expensive endpoint receives
only overflow/failover traffic. No ramp routes users away from a healthy,
capable, unconstrained Parakeet target to exercise an expensive endpoint.

Production and development remain `STT_ROUTING_MODE=shadow` and
`STT_ROUTING_ON_PERCENT=0` on merge. Observe proposed/static primary agreement,
health transitions and outcomes first; then set `on` with percentages 5 → 25 →
100. The router cohort is `sha256("stt-routing-on:" + uid)` and never changes
Parakeet's allocation cohort. In active routing the old language-arm/primary
pin does not supersede capability and cost. `STT_ROUTING_ON_PERCENT=0`,
`STT_ROUTING_MODE=shadow`, or `off` restore static selection immediately through
runtime config. `PARAKEET_WINDOW_ALLOCATION_PERCENT=0` independently withdraws
windowed Parakeet. No deployment or production qualification is part of these
local test results.

New bounded metrics: `omi_stt_cost_routing_decisions_total{target,reason}` with
`capability|cost_primary|benched_skip|ramp_skip|capacity_skip|failover`,
`omi_stt_cost_routing_benched{target}`, `omi_stt_cost_routing_stage{target}`,
`omi_stt_cost_routing_shadow_total{agreement,target}`, and
`omi_stt_cost_routing_events_total{target,event}`. Decisions count the proposed
policy even in shadow; capacity admission refusals also count actual overflow
in active mode. The event counter counts fleet transitions; local Redis-down transitions are
logged with `scope=local` and do not increment it again. Transition logs contain
target, bounded language, scope, stage, n,
failures, rate and cooldown, never UID/content/endpoint/credentials. Gauges
reflect the last queried language per pod: use event logs for language diagnosis.
Add dashboard panels for proposed target share, shadow disagreement, maximum
bench state, minimum recovery stage, transition counts, and dropped writes.
Use traffic floors/dwell for alerts and the existing headline transcript SLI;
no unvalidated Grafana rule changes are included here.
