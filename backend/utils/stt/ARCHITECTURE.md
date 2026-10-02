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
`batch_pressure.py` owns the off-path GPU-pool poller and cached admission:
per-replica last-good samples expire after 15 seconds, fresh quorum requires
both the configured minimum and a strict majority of DNS-ready pods, and busy
plus unknown pods reaching half the pool stands down. Individual fetch failures
retain their timestamps; DNS failure invalidates the fleet. Its fan-out/cache
cap is 64 pods and admission never performs I/O.
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
failover. Eligibility also uses the session's actual precomputed family engine:
windowed Parakeet must have won the existing window/RNNT selection, pass
`window_language_supported`/`window_allocation`, and have its hosted endpoint.
Connect validates target/model/endpoint identity; a mismatch counts a bounded
`engine_mismatch` fail-open and restores configured order. RNNT outcomes are
never labelled as window outcomes.
An empty proposal always restores the configured chain. A nonempty proposal
appends configured services outside the proposal (including unregistered
Deepgram), then eligible benched targets as last resorts. Bench means demotion
when every better connection fails, not denial of service. Local account and
capacity protections still apply; this tail does not generate proactive probes. Capability checks include every expected language from the immutable
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

Health alone cannot empty an eligible chain. If all capacity-available targets
are degraded, order them by highest stage, lowest observed provider-error
fraction, then cost (config order breaks ties), and expose `all_degraded`.
This emergency chain may exceed trial admission shares because there is no
healthy alternative. Otherwise the most expensive available target is not
restricted by its health/trial share unless a cheaper stage-100 candidate can
absorb this UID's traffic. Health-skipped trial/bench targets stay at the
last-resort failover tail. Explicit registry ramps, actual engine/capability
eligibility and account protection are never bypassed. If all candidates are
capacity-blocked, propose the least-recently-refused chain and allow the
existing one-dial-per-session capacity escape. Empty still means no eligible
registered target (for example a withdrawn ramp or account-only quarantine),
invalid config/cache error, or a legacy-only configured family; it restores
configured order and must not be hidden by a misleading healthy proposal.

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

`live_gate.py` uses three Page CUSUM log-likelihood scores. At the default
`STT_ROUTING_DISRUPTION_GATE=0.08`, alternatives are 0.12, 0.16 and 0.60;
for another gate g they are g + (1-g) times 1/23, 2/23 and 13/23.
Each score updates as `max(0, score + log P_q(outcome)/P_g(outcome))`.
Bench thresholds are 12, 11 and 10 respectively, with at least eight classified target/session outcomes. The rapid 60% alternative additionally needs eight failures in the
last 32 sessions, so five failures after a long healthy history cannot alone
trigger it. Scores continue across reporting-counter boundaries; there is no
1,024-session test reset or repeated injection of fresh likelihood mass.
This is an empirically calibrated change detector, **not an anytime-valid
e-process, posterior probability or formal lifetime alpha guarantee**.

A healthy target's fleet-wide bench requires at least four distinct failure
UID fingerprints in the last 32 sessions, with no one UID supplying more than
half of those failures. A smaller language cohort can bench only its language
with at least two affected UIDs, sixteen recent failures, and a score >=14.
One caller cannot bench a healthy target or language. Recovery promotion uses
session count plus passing user-vote rate, without a distinct-user floor. A failed
30/60-session recovery boundary must satisfy the same four-failing-user,
no-majority breadth rule before re-benching the fleet and spending a strike.
Narrow failures hold the current trial share without a fleet strike; the
healthy-stage stronger two-user test may bench only their language. Fingerprints are bounded salted
SHA-256 prefixes, never raw UIDs, labels, logs or content.

Calibration uses 200 independent seeded runs of 20,000 sessions per baseline
rate, resetting after false benches to count all episodes:

| True provider-error rate | False benches / 4,000,000 sessions | Runs with a bench / 200 | Episodes per 252,000 sessions (14 days at 18k/day) |
| --- | --- | --- | --- |
| 3% | 0 | 0 | 0 observed |
| 5% | 1 | 1 | 0.063 |
| 7.5% | 24 | 22 | 1.512 |

The 3% experiment covers about 222 traffic-days. Zero observed events does not
prove impossibility; the one-sided 95% upper bound on a 20k-session run having
a false bench is about 1.49%. Near-gate 7.5% traffic has appreciably more false
benches than the 3% baseline; the detector trades this for useful brownout
sensitivity. Independent synthetic outcomes are not production qualification.

Across 200 seeded outage runs after 500 healthy sessions:

| True provider-error rate | Median sessions to bench | 95th percentile sessions | Median / 95th percentile failed sessions |
| --- | --- | --- | --- |
| 60% | 13 | 21 | 8 / 10 |
| 80% | 10 | 13 | 8 / 8 |
| 100% | 8 | 8 | 8 / 8 |
| 16% (2x gate) | 264.5 | 557 | 44 / 78 |
| 12% | 972.5 | 2362 | 119 / 249 |

Periodic 60% outage tests cover every phase and 0/100/1020/20,000 healthy
warmups and bench within ten failed sessions. A stochastic 60% outage does
not guarantee that bound for every possible random sequence; its measured
95th percentile is ten failures. At 10%, there is **no prompt-bench SLA**:
only 101/200 seeded runs bench within 5,000 sessions; censored median 4975.5.
Changing the configured gate clears accumulated scores without clearing an
existing bench. A hard outage's wall time depends on completed speech-session
volume: eight failures at 62 sessions/5 minutes take about 39 seconds at full
traffic or 155 seconds at 25%, plus outcome and cache delays.

The v5 gate measures provider-path availability, separate from transcript/audio
quality. `live_signal.provider_observation` classifies one outcome per leg:

- Completed text after at least one second of VAD speech is a non-failure.
  Actual text received after the diagnostic deadline also qualifies.
- Serving death/failover counts only for `modulate_serve_error`,
  `connection_lost`, `send_failed`, `provider_5xx`, `provider_rate_limited`,
  `provider_429`, or `timeout`. Provider transport availability includes the
  backend-to-provider path; this is not proof of a vendor incident.
- Connect errors with those reasons also count once per target attempt, even
  before speech. Account/config/capacity failures retain their separate gates.
- Plain `no_text`, `first_text_deadline`, `empty_streak`, VAD/client failure,
  idle/rotation and account/capacity outcomes are **censored**: neither numerator
  nor denominator, and they cannot advance a trial. Existing leg no-text and
  conversation transcript counters remain diagnostic and unchanged in shadow.

`live_reason.normalize_live_stt_reason` owns the closed 27-token vocabulary
used by both cost observations and source-leg fallback metrics. The serving leg
latches the first bounded cause: socket-owned typed reason, bounded raw socket
reason, then the send/monitor symptom. Unknown/free-text transport death is
`connection_lost` (or `send_failed` for a direct send failure), deliberately
provider evidence; explicit window/session/account causes are censored.
Provider and window sockets publish cause metadata before their death latch.
A failed hop keeps its source reason even when its successor rejects the
connection; that rejection determines settlement outcome, not source attribution.
Observation labels are target/outcome/reason, never raw diagnostic messages.

No-text deadlines no longer seal health evidence early. Completed text waits
until close; later attributable death therefore wins, once. Intentional client
teardown is censored. A deadline-only window failover is not a hard failure,
regardless of its successor: aggregate data has no successor/session join,
and adding a cross-leg adjudication is outside this calibration. This loses
automatic gate detection of a recognizer that connects but silently returns
no words; watch deadline and conversation transcript SLIs for that incident.
The prior 5–7% VAD/no-word floor must not become provider-error evidence.

At independent 5%, 7% and 10% no-text floors with zero provider errors, each of
20 seeded 20,000-session replays observed **0 false benches / 400,000 sessions**.
For this clean v5 state and correctly classified zero-error condition, the
false-bench probability is exactly zero: censored outcomes do nothing and
successful outcomes cannot increase a CUSUM score. This is a conditional
classification guarantee, not a lifetime guarantee when real errors exist.
The older calibration table above now concerns genuine provider-error inputs.

With a 10% censored noise floor, after 500 healthy outcomes, 200 seeded runs
measure these total speech-session and failed-session detection counts:

| Attributable error fraction of speech sessions | Median / p95 total sessions | Median / p95 failures |
| --- | --- | --- |
| 100% hard outage | 8 / 8 | 8 / 8 |
| 60% hard outage | 13 / 19 | 8 / 9 |
| 40% Modulate-like brownout | 22 / 47 | 9 / 15 |

The 100% case has no residual noise slots. Stochastic p95 is not a worst-case
bound. Tests bound Modulate-like median at 30 and p95 at 50 sessions in this
seeded model. At 62 speech sessions per five minutes, 47 sessions is about
3.8 minutes at full traffic, before completion/cache lag. Low-volume targets
or 5% trials require longer wall time. The gate remains 8%: after censoring,
measured healthy provider errors are about 0.3–1%, not the 5–7% audio floor.
A relative cross-provider baseline would add language/traffic-mix and fallback
selection bias without resolving this attribution error.

Target-global and bounded-language tests remain independent. A language bench
can restrict that language; sparse healthy languages inherit global health.
The language view is used after 30 classified samples or a decisive test.

A bench waits 300 seconds initially. Failed trials double the wait up to
four hours. A fleet lease starts a shared 5% trial when that target would be
preferred over surviving targets. Trial promotion counts only classified outcomes and gives each observed user
one vote: a user is failing when more than half of their speech sessions in
the current window fail. Promote after at least 30 sessions at 5%, or 60 at
25%, when the failing-user fraction is <= the configured gate (default 8%).
A healthy single-user trial still promotes. Per-user sequential evidence is
limited to its first three outcomes per window; repeated failures cannot
accumulate a language alarm while contributing only one promotion vote.
The user's majority vote nevertheless updates from **all** their window
outcomes, so late widespread failures can reject at the 30/60 boundary.
Trial rejection needs an above-gate user rate and four failing users for a
fleet strike. The healthy-stage session CUSUM and its sparse-language rule
are unchanged.

At 120/240 sessions, a held trial starts a new user-vote/evidence window,
retaining stage, strikes and generation. State stores at most 240 hashed UID
fingerprints, bounded outcome counts, and no content. Here is a deterministic
coverage bound: with no more than two always-failing users and at least 23
always-passing users observed within each stage's 120/240-session window
(>=92% healthy observed users), the global and language trials reach 100%
within **360 classified trial outcomes**, regardless of how many of
those sessions the two callers supply. Censored noise does not advance this bound. If each 30/60-outcome prefix already
has that coverage, the bound is 90 sessions. Coverage concerns each sticky
stage cohort; a target-wide healthy majority that never appears in the trial
cannot establish recovery. There is no unconditional raw-session or wall-time
bound under arbitrary user arrivals, nor a statistical guarantee from 23 votes.
Broad outages still bench early from sequential evidence. Acceptance votes
do not prove an 8% confidence bound. Strike history clears after 1,024 healthy
observations.
Expensive benches receive no primary probes while cheaper targets can serve;
they remain available only at the failover tail. No pod privately restarts a
trial during Redis faults. Trial evidence must belong to the sticky re-entry
cohort intersected with the target ramp. Stage generations reject stale
completions, including samples admitted from a stale snapshot.

The daily Modulate trial replay models 17,900 eligible speech sessions/day,
61% disruption, sticky UID admission, 30-second outcome delay, 15-second cache
lag, and initial 5-minute cooldown doubling to the 4-hour cap. Across 100 seeds,
mean trial traffic is 122.08 sessions/day; mean disruptions **75.46/day**, median
75, p95 80, maximum 83. Every run must remain below 100 trial disruptions;
allowing ten initial outage failures still stays below 100 (maximum 93).
A constant 5% trial without benches/backoff would instead expect
`17900 * 0.05 * 0.61 = 545.95` disruptions/day. This is a conditional replay
budget, not an absolute production traffic cap: burst arrivals, correlated
heavy UIDs, longer outcome delays and dropped writes can change exposure.
Local breakers are omitted from the replay, so their additional protection
is not credited. Other providers' failures are outside this trial budget.

`live_cost_health.py` stores target/global and target/language state in the
`omi:live-stt:cost-v5` Redis namespace. Compare-and-set updates preserve shared
counts and transitions across pods; leases serialize trial starts. Fleet
bench deadlines and trial admission use Redis `TIME`, not pod wall clocks.
Redis-down local deadlines use the last known server offset and translate once
on recovery before CAS reconciliation. Tests cover opposite +/-60-second pod
skews and a ten-minute Redis outage with sixty successful connection decisions.
The v5 namespace prevents v3 audio/no-text and misclassified v4 evidence from
being reinterpreted as provider errors. It starts fresh shadow history; warm it before raising on-percent.
A background refresh uses the existing 75 ms deadline. Connect reads memory only. Redis
faults use local evidence and retain known benches, then unknown health and
configured cost order. A router exception restores today's configured chain. Local benches backed by failed Redis writes remain restrictive when Redis returns, and are reconciled
through CAS before staged recovery; snapshot and generation capture use the
same freshness/backoff predicate. Fresh shared health remains authoritative
over an isolated pod's local rate; verified writes refresh the local fallback
view so a later Redis blip cannot revive a stale pod-only bench.
Account/billing refusals remain family-wide immediate protection. Connection
and serve breakers remain fast local protection; a fleet bench demotes its
target to the last-resort tail, with no forced account bypass.
Targets with an active capacity signal or local capacity cooldown are excluded
from terminal legs and their configured-default aliases. A `capacity_full`
refusal starts a five-second, monotonic process-local target cooldown, including
on empty-proposal configured fallback. It releases any circuit probe without
recording a circuit failure or fleet health disruption. Static off/shadow
connections retain existing behavior; active capacity cooldowns cannot be
bypassed by the static last-resort force path. If **every** remaining candidate
is capacity-signalled or cooled, permit one least-recently-refused candidate
through its normal circuit/admission gate. This escape makes at most one dial
per session and never bypasses account protection. A still-full sole candidate
can therefore receive one attempt per session; a five-second process-wide
attempt bound would strand sessions when it recovers earlier. With an
alternative available, overflow cooldown protection remains unchanged. Retain
refusal timestamps for ordering, bounded to 64 IDs; evict the oldest on churn.
Legacy provider-score state is retained for static protection/telemetry but
never ranks the active cost router. Registry fields and endpoint URL structure
are validated before selection. Actual same-family initial overflow emits
shared fallback telemetry; normal cost-selected primaries do not. Reconnects
retain target identity. Initial connects and mid-session rebuilds use separate
failed-target and failed-family sets. Ordinary serving deaths exclude only the
selected target; typed quota/auth deaths exclude the family and its siblings.
The receiver builds on #20157's replay/retry behavior without discarding capture.

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
`omi_stt_cost_routing_shadow_total{agreement,static_primary,proposed_primary}`, and
`omi_stt_cost_routing_events_total{target,event,scope}`, and
`omi_stt_cost_routing_fail_open_total{reason}` with bounded
`empty_proposal|engine_mismatch|cache_unavailable|router_error`. Primary and skip decisions count the proposed policy even in shadow;
`failover` counts actual active backup attempts, and capacity admission refusals
count actual overflow. Unused backup legs do not inflate failover counters.
`omi_stt_cost_routing_all_degraded_total{target}` marks the emergency health
selection, and `omi_stt_cost_routing_observations_total{target,outcome}` separates
`success|provider_failure|censored`. No UID/content labels are added.
Transition counters count successful CAS writers, separately for
`scope=global|language`; Redis-down local transitions remain logs only.
All target/event/scope counter series are initialised at zero before traffic,
including custom registry IDs. This makes a first post-scrape increment visible
to `increase()`. Events before a pod's first scrape are inherently unobservable
as increases; counters are not a durable fleet event ledger.
Transition logs contain target, bounded language, scope, stage, n, failures,
rate, score and cooldown, never UID/content/endpoint/credentials. Their rate
is classified session outcomes; trial promotion uses user votes.

Stage/bench gauges are **pod views of global target state**, not a central
fleet gauge. The old code published on selection/events only and refreshed
only traffic-interest keys: an idle or Parakeet-ineligible pod could retain
100 despite a remote trial. v3 already selected the global state, so the code
provides no evidence of language-state leakage into that gauge. Every v5
background refresh watches all registry global keys and republishes gauges,
even without eligible sessions. Unknown health is NaN, with
`omi_stt_cost_routing_state_known{target}=0`, not a claimed healthy 100.
`omi_stt_cost_routing_snapshot_timestamp_seconds` uses Redis time for the
last complete snapshot; NaN denotes never refreshed, finite old time denotes
stale. Require freshness/known state and convergence before
interpreting pod min/max; Redis faults can retain a local fallback view.
Shadow pair labels are validated registry IDs (maximum 16), plus fixed
`unregistered`/`unavailable` sentinels. Metrics schema changes require draining
old pods before scope/freshness queries become authoritative.

Add dashboard panels for proposed target share, shadow disagreement, maximum
bench state, minimum recovery stage, transition counts, and dropped writes.
Use traffic floors/dwell for alerts and the existing headline transcript SLI;
no unvalidated Grafana rule changes are included here.

### Aggregate shadow replay (2026-10-02)

The uncommitted 48-hour, five-minute Prometheus export was replayed locally.
During 19:00Z–03:00Z, Parakeet and Soniox remained 100 with zero transitions;
Modulate first benched around 19:02Z, then cycled 0/5 with exponential backoff,
never reaching 25/100 again. Empty proposals: **0**. Proposed primary shares:

| Synthetic cohort/capability model | Parakeet | Modulate | Soniox |
| --- | --- | --- | --- |
| Existing static primary as eligibility proxy | 18.330% | 3.624% | 78.047% |
| Independent sticky 25% cohort + observed language mix | 23.063% | 3.238% | 73.699% |
| Full 48h export, independent cohort | 22.638% | 2.741% | 74.621% |

Both 8h models keep healthy targets at 100 and Modulate unhealthy, with no
empty proposal. Results use synthetic distinct callers, interpolated bucket
ordering, and disjoint death/first-text observations that conservatively
dilute error fractions. First-text counters are not completed-leg counters.
No aggregate session join can reconstruct exact user repetition, language
failure allocation, successor results, engine/cohort correlations or delayed
completion generations. The 48h export has router proposals only after its
rollout; re-entry cannot be inferred before that. These are diagnostic
counterfactuals, not exact historical sessions or production qualification.
The shipped synthetic 24h test independently covers measured 3–8% Soniox
noise + 1% errors, 6–10% Parakeet noise + 0.3% errors, and 40% Modulate errors.
