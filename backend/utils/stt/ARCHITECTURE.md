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
- `live_recovery.py` permits one healthy Soniox re-entry after transient transport
  loss; receiver attempt counting and a terminal latch bound retries independently
  of the distinct-provider exclusion set.
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
A canary empty proposal keeps only the permitted unregistered legacy tails —
registered static services that the filter withdrew are not restored; a
nonempty proposal appends permitted configured services outside the proposal
(including unregistered Deepgram), then eligible benched targets as last
resorts. Cache unavailability and router faults under a valid registry fail
open to the filtered static chain; a canary caller instead keeps its permitted
registry target routes so target-scoped evidence, endpoint/credential breakers
and replay declarations survive the outage — states carried by
`CostHealthUnavailable` demote known restricted entries behind unrestricted or
unknown ones (higher restricted stage first, configured order for ties) but
never clear them, while a generic router error carries no snapshot and keeps
pure configured order; a malformed registry or account-snapshot
malfunction fails closed for managed sessions, while UID-less legacy callers
keep the filtered static fallback under the same account/capability checks.
Every connection
path passes one permission helper (`permitted_target` in `live_router.py`):
the actual family engine, target capability for the requested and every
expected language, the sticky registry ramp (zero/partial ramps without cohort
proof withdraw the target), and an active account quarantine all deny dialing.
The filter applies to proposal candidates, last-resort tails and the static
fallback in `on`, `shadow` and `off` modes alike; the account snapshot is read
even when routing is off, and Deepgram honors it like every other family.
A registered endpoint-less target matching the actual engine owns the default
endpoint's permissions — a custom endpoint entry does not withdraw it, and an
unmatched engine keeps only its unregistered capability/account checks. When
filtering empties the whole chain, `NoPermittedTarget` (a
`ProviderChainUnavailable` subclass) raises with a bounded retry after the
longest remaining account quarantine, otherwise five seconds, and the unlabeled
`omi_stt_cost_routing_no_permitted_target_total` counter increments. Router
exceptions and cache unavailability with a valid registry fail open to the
same filtered chain — canary sessions keep permitted registry target
identities, non-canary sessions keep the filtered static chain — never the
raw configured order. An invalid
`STT_ROUTING_TARGETS_JSON` cannot establish permissions: managed routing
sessions get the typed chain-unavailable plus a `router_error` fail-open
rather than a default that could reopen a withdrawn target; UID-less legacy
callers keep the static fallback under the same account exclusions. Bench means demotion
when every better connection fails, not denial of service. Local account and
capacity protections still apply; this tail does not generate proactive probes. Capability checks include every expected language from the immutable
declared/learned session profile, so a declared English account with a learned
Hindi prior cannot enter an English-only target. Healthy cheaper targets take every eligible session within their
configured ramp and capacity. There is no portfolio split or worst-provider
probe. The existing Parakeet admission and batch-pressure gates still reject
at connect and overflow into the next target. Recovery target IDs stay
distinct per registry entry, while connection breakers key on provider plus
actual endpoint plus stage with the credential synced as account identity —
two Modulate targets on the same wire share one breaker but still fail
independently as recovery candidates, and credential rotation clears only
account/quota state without erasing the unchanged endpoint's outage evidence.
A narrow typed-death hook routes a custom endpoint's serving failure
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
invalid config/cache error, or a legacy-only configured family; on canary it
serves only the permitted unregistered tails, while a fault falls back to the
filtered configured order and must not be hidden by a misleading healthy proposal.

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
its existing `sha256("parakeet-window:" + uid)` cohort. Its effective ramp is
the minimum of the registry percentage and that allocation, so neither control
can exceed the other; registry `ramp_percent` defaults to 100 and
`PARAKEET_WINDOW_ALLOCATION_PERCENT` defaults to 0, unchanged. Other target
ramps use the same hash shape with their target ID. Recovery uses a separate, nested sticky cohort, so a 5%
re-entry means 5% of sessions eligible under the configured ramp.

### Serving-owned health evidence (cost-v8)

`live_outcome.LiveLegOutcome.settle` is the single emission seam. Each managed
leg owns one outcome. Observing `is_connection_dead` is pure; send only latches
a bounded cause. The serving owner claims that outcome when it decides to
replace the leg, rejects its connection, or exhausts recovery. `PendingLiveFailover`
carries the claimed source until settlement and invokes the seam, which emits
both `omi_fallback_total` and the matching cost observation synchronously.
Connect rejections use the same object, including a socket rejected just after
upgrade. There is no supplementary connect writer or per-writer receipt.

A hop is recovered only on successor text. Failure/cancellation/teardown settles
it as degraded or exhausted. A 30-second telemetry timer settles an unresolved
managed hop as degraded: a silent successor cannot hide the source failure.
The timer does not close sockets, alter audio, retry, or declare recovery.
Terminal serving deaths with no remaining successor now emit one exhausted
`stt_live_session` fallback and one observation. A second pending object,
monitor/send race, repeated close, or late transcript cannot settle the same
source twice. Actual text counts without a VAD minimum, as do accepted provider
deaths before the first audio byte.

Owner teardown is marked before receiver tail sends and before drain. It cannot
claim a provider failure from a transport symptom. A death already latched before teardown is settled before the owner fence,
even if the polling monitor has not claimed it. A previously claimed source
keeps its cause through cleanup. Connect-time censored
causes release circuit admission without adding provider failures; local VAD
failure cannot open a provider circuit at terminal settlement either. Ordinary finish/drain emits
success if text was observed, otherwise censored no-text; neither a liveness read nor a late raw symptom independently writes health. PTT/custom/BYOK/multichannel remain outside the
managed cost-evidence population. Their legacy fallback telemetry is not a
cost-router observation and must not be joined as though it were one.


Client eligibility is checked at the first serving claim: explicit disconnect,
inactive state or shutdown excludes that death without a fallback emission.
Already claimed connected-client evidence survives later departure. Excluded
legs retain prior text as success or settle censored no-text; repeated observers
cannot resurrect them. The bounded ignored-death counter diagnoses that boundary.
This v7 eligibility correction changes no transport, recovery, circuit or ramp
behavior relative to the merged serving-owned settlement implementation.

| Terminal decision | Fault domain | Existing fallback reason | Router observation |
| --- | --- | --- | --- |
| Completed text / owner end | none/client | none | success/text |
| No text / client disconnect / our close | audio/client/us | none | censored/no_text or normal_close |
| Accepted provider death, with or without prior speech | provider/path | modulate_serve_error, connection_lost, send_failed, provider_5xx, provider_429, provider_rate_limited, timeout | provider_failure, same cause |
| Connect transport/server failure | provider/path | provider_5xx or timeout | provider_failure, same cause, path=connect |
| Quota / authentication | account/us | quota / auth | censored/provider_budget_exhausted or provider_auth_rejected (connect auth remains auth) |
| Window first-text deadline / empty streak | unresolved audio/recognizer | first_text_deadline / empty_streak | censored, same cause |
| Admission, capability/allocation, PCM/replay/send-queue capacity | us/capacity | capacity_full / allocation_rejected / capability_mismatch | censored, same cause |
| VAD / invalid request or audio / loop misuse | us/audio | vad_failed / other | censored, same cause |
| Soniox 400 no-audio / 408 request timeout | client/input timing | soniox_idle_timeout / soniox_request_timeout | censored, same cause |
| Soniox duration rotation | protocol lifecycle | soniox_rotation | censored/soniox_rotation |

The closed reason vocabulary stays in `live_reason.py`. Socket-owned typed
causes precede bounded raw causes and observer symptoms. Unknown transport death
is `connection_lost`; known local queue/loop failures are explicitly censored.
Modulate's recognized invalid-input frames use `other`, while its typed serve
errors remain provider failures. Soniox publishes reason metadata before its
death latch, so an observer cannot consume an uninitialized cause. No transcript,
audio, UID, endpoint, or free-text diagnostic enters labels or transition logs.

### Fair evidence and gate calibration

The 8% Page CUSUM is retained: alternatives 12%, 16%, 60%; thresholds 12, 11,
10; minimum eight admitted outcomes, with eight failures in the recent 32 for
the rapid alternative. This is an empirical change detector, not a posterior or
an anytime-valid probability guarantee. Correcting attribution removes the
5–7% no-word noise floor; increasing the threshold would hide real outages.

Healthy-stage evidence admits at most **three classified outcomes per UID
fingerprint per target/scope per five-minute Redis-time window**, symmetrically
for success and failure. At most 2,048 ordinary domain-separated SHA-256 prefixes plus eight outage
witnesses are stored per state. Ordinary capacity exceeds the 1,500
identities/window at 10x 1,800 sessions/hour. At saturation, eight distinct new users failing without an intervening
classified success bench the target. Any success (even capped) resets the
reserve, preventing low-rate failures from accumulating as failure-only CUSUM
samples. One caller cannot fill it; eight witnesses cannot exhaust it without
benching. Existing identities retain their three-vote cap; no eviction restores
a budget. Normal brownout evidence is sampled above capacity, so `votes_total{result="window_full"}`
must remain zero. CAS applies the cap across pods. Raw observations still count
every settled leg for reconciliation; the separate votes metric explains which
observations reached the gate. No raw UID is stored in Redis.

A global bench still requires four failing fingerprints, no one contributing
more than half the recent failures. Sparse language benches require two affected
users, sixteen admitted recent failures and score >=14; the cap means two or
three repeating callers need several windows, rather than one reconnect burst.
A language restriction is independent of the global stage, which remains the
only state exported by the stage gauge. Promotion uses 30/60 **admitted** trial
outcomes (stage 5→25 requires 30, stage 25→100 requires 60), at least **10/20
distinct witness fingerprints** respectively, and a **300/600-second trial
dwell** measured from `trial_started_at` on the Redis clock — a completed
admitted window before the dwell holds at its stage. Per-witness votes stay
capped at three admitted success/failure outcomes per trial window, so one
repeated caller can neither fill the sample nor be a majority. Promotion also
requires the majority-failure fraction across trial users at or under the gate;
broad failures (at least four majority-failing users) re-bench, and anonymous
simulation outcomes cannot promote because breadth cannot be proven. A witness
whose three-outcome cap is already spent admits nothing new, but its return
still re-evaluates the frozen cohort: once dwell has elapsed it promotes from
the admitted evidence and the vote is counted `user_cap`, not `applied`. Held
windows reset at 120/240 admitted outcomes. Re-entry remains 5 → 25 → 100 with
shared leases, generation fences and a 300-second initial cooldown doubling to
four hours.
Expensive benches receive no primary probes when a cheaper target can serve.

Reproduce the v6 calibration from `backend/`:

```sh
.venv/bin/python scripts/stt/calibrate_live_gate.py
```

Twenty seeded runs of 20,000 sessions use 1,000 returning synthetic users at
17,900 sessions/day. Every row below observed **0 false benches / 400,000 raw
sessions**: 0% provider error with 5%, 7%, or 10% censored no-text; and 0.3%,
1%, or 3% provider error with 10% censored no-text. This is empirical evidence,
not a promise of zero false alarms for all future correlated workloads. With
zero actual errors, censorship makes an audio-only false bench impossible.

Two hundred seeded detection runs after 500 passing outcomes give:

| True provider failure rate | Median / p95 sessions to bench | Median / p95 failures | Maximum sessions observed |
| --- | --- | --- | --- |
| 40% | 20 / 48 | 9 / 15 | 87 |
| 60% | 13 / 21 | 8 / 9 | 31 |
| 100% | 8 / 8 | 8 / 8 | 8 |

Injecting 46 additional passing reconnects from one UID does not change these
non-churn-session distributions. At 62 representative sessions/5 minutes,
48 sessions is 3.9 minutes, plus at most 30 seconds of hop settlement and the
snapshot delay (normally 5 seconds; stale at 15). Eight hard failures are about
39 seconds plus those delays. Low-volume fallback targets and exhausted user
budgets take longer; at saturation a user may wait the remainder of five
minutes for a new vote. There is no raw-session/wall-time guarantee without
traffic breadth. Read admitted shared votes when diagnosing detection speed.

### Fleet state and operational limits

`live_cost_health.py` stores target/global and bounded-language state under
`omi:live-stt:cost-v8:<stage>:<32-hex identity>:<target>:<language>`; recovery
leases sit under the same cost prefix, never under the fleet namespace. Fleet
state splits two `omi:live-stt:fleet-v2:<stage>:<32-hex identity>` scopes:
endpoint scope (SHA-256 of `live-stt-fleet-v2-endpoint`, family, actual serving
endpoint and family credential) owns selection benches, recovery probes and
score buckets, and account scope (SHA-256 of `live-stt-fleet-v2-account`,
family and credential) owns the credential-wide account quarantine.
`config/live_stt_state.py` owns the key helpers: `stage` comes from
`OMI_ENV_STAGE` (`prod|dev|local|offline`, else `unknown`, never defaulted to
prod; an unrecognized stage still yields `offline` when
`PROVIDER_MODE=offline`). Parakeet's endpoint is `HOSTED_PARAKEET_API_URL`,
Modulate/Soniox use their configured or built-in endpoint and API key. An
account quarantine therefore spans every custom endpoint sharing one credential,
while a rotated endpoint starts only endpoint-scoped selection/score/probe and
cost state fresh — the shared account bench persists until its own expiry or a
credential change. Registry targets carrying their own `endpoint` partition that scope one
level deeper: transcript outcomes, serve-death and connect-rejection
selection benches, local scores, interests, pending writes and probe leases
are partitioned per actual serving endpoint (provider for the configured
default, `provider@<fleet prefix>` for a custom endpoint), so a sibling
endpoint's evidence never moves the default or another sibling. Account
writes and reads stay family-scoped and dominate every sibling's selection
bench; a snapshot merges the queried endpoint's selection bench with the
family's strongest live account deadline. Custom target circuits key on a
provider+endpoint+stage selection fingerprint rather than the target id, so
alias/cost/ramp edits reuse a breaker while an endpoint or stage rotation
gets a fresh one; the cache is bounded at 64 entries. Process-local
selection breakers retain connect/serve outage evidence across credential
rotation for an unchanged endpoint: credential rotation clears
account/quota state only, endpoint changes start fresh selection state
while an unchanged credential's account protection remains, and stage
changes start fresh scoped state. A custom endpoint's serve death opens
that endpoint's local target breaker and does not bench the family default.
The Redis fleet/cost namespaces still include the credential in their
digests, so shared state still starts fresh on rotation.
While `STT_ROUTING_MODE=off`, snapshots return a neutral score with zero
samples and merge only family account benches — local and cached selection
benches and scores are ignored without being erased, so toggling back on
retains routing state. In-memory views reset on an identity boundary instead of
mixing identities, and in-flight writes cannot populate a new identity's
cache. v7/v1 and older namespaces are never read, migrated or backfilled.
Raw URLs and credentials never enter Redis paths, logs or metrics.
Redis TIME owns windows and cooldowns; CAS preserves counts and stages across
pods. Connect reads a cached snapshot, with Redis refresh/result work in bounded
background tasks under the existing 75 ms deadline. Redis failure retains local
evidence and known benches; no pod privately restarts a trial. Local benches
reconcile before staged recovery, and generation fences reject stale completions.
Fleet bench writes are one Lua update over both state keys: a live account
quarantine rejects a selection write and is never shortened, each kind keeps
the longest deadline on its own key, a selection write never expands an
account fault domain, and the returned retained value merges back into the
writing pod's local view so a stale pod immediately learns a stronger
quarantine. Refresh reads both state keys and prefers an active account bench,
then the endpoint selection, then the expired account for its probe lease.
Expired cleanup is a compare-delete per namespace that re-reads the observed
value and its deadline inside the script before removing that namespace's
state and probe together — a bench renewed between the text read and the
delete survives, and an expired account cleanup never touches endpoint state.
Each off-connect refresh reads every registry target across the closed bounded
language vocabulary (Modulate ∪ Parakeet supported languages plus `other`,
capped at 16 targets) plus `all`, not only live interests. Freshness is tracked
per `(target, language)`: an explicit missing Redis key marks that key read and
healthy, a global timestamp never fresh-marks an unread language, and
`_cost_update` marks only the key it wrote. A snapshot whose requested language
is unread and unconstrained by a retained lower-stage bench raises
`CostHealthUnavailable` instead of claiming stage 100; cold Redis-down views
retain local and known benches. `omi_stt_cost_routing_language_state_total`
counts each per-target comparison (`agree|language_restricted|
global_restricted|unknown|stale`) with no language, endpoint, account or UID
labels.
Connect rejection captures the generation at rejection, not before its handshake.
Healthy keys expire after 900 idle seconds (three windows). Bench and trial
states have no healthy-window fingerprints and deliberately persist: expiration
must not silently turn an unprobed expensive bench into a fresh stage-100 target.
The emission acknowledgement and paired settlement/observation counters check
only emission, not omitted terminal paths, classification correctness or Redis
durability. Separate chain-handoff, physical-open and terminal-settled counters
provide a lifecycle coverage oracle; a gap persisting over two minutes is a
rollout stop. Write drops and admitted votes check the asynchronous persistence
path. Exact PromQL is in the live routing runbook.

Health stages may demote but cannot empty an otherwise eligible chain. Explicit
ramp/capability/account exclusions stay hard in the active chain: a withdrawn
registered default endpoint cannot return disguised as an unregistered static
tail. Unregistered configured families retain their legacy tail; a canary empty
proposal keeps only those permitted tails, while a router exception still fails
open to the filtered configured chain. Local account/serve
circuits and window admission/pressure gates remain fast protection. Target
identity is preserved across same-family endpoints; account failures quarantine
the credential family. Capacity refusals keep their five-second local cooldown
and one-attempt all-capacity escape.

Accepted non-window streams that keep returning no words are consciously not
benched by this availability detector. `STT_NO_TEXT_SECONDS` remains diagnostic;
no speech/no-word timeout is added to serving. The leg no-text counter updates
while audio flows, and the existing conversation transcript-success alert covers
completed sessions. A quiet connection that emits nothing indefinitely has no
new per-session rescue here. The runbook makes no-text/first-text SLIs mandatory
and requires checking the live alert route; no content join or acoustic judgment
is inferred from VAD alone.

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
`STT_ROUTING_MODE=shadow`, or `off` restore static selection after the runtime
configuration deployment. `PARAKEET_WINDOW_ALLOCATION_PERCENT=0` independently withdraws
windowed Parakeet. No deployment or production qualification is part of these
local test results.

New bounded metrics: `omi_stt_cost_routing_decisions_total{target,reason}` with
`capability|cost_primary|benched_skip|ramp_skip|capacity_skip|failover`,
`omi_stt_cost_routing_benched{target}`, `omi_stt_cost_routing_stage{target}`,
`omi_stt_cost_routing_shadow_total{agreement,static_primary,proposed_primary}`, and
`omi_stt_cost_routing_events_total{target,event,scope}`, and
`omi_stt_cost_routing_fail_open_total{reason}` with bounded
`engine_mismatch|cache_unavailable|router_error`,
`omi_stt_cost_routing_no_permitted_target_total` (unlabeled) when the
permission filter empties the chain, and
`omi_stt_cost_routing_language_state_total{target,comparison}` with
`agree|language_restricted|global_restricted|unknown|stale`. Primary and skip decisions count the proposed policy even in shadow;
`failover` counts actual active backup attempts, and capacity admission refusals
count actual overflow. Unused backup legs do not inflate failover counters.
`omi_stt_cost_routing_all_degraded_total{target}` marks the emergency health
selection, and `omi_stt_cost_routing_observations_total{target,outcome,reason}` separates
`success|provider_failure|censored`. The paired
`omi_stt_cost_routing_settlements_total{target,outcome,reason,path}` records the
serving seam's expected evidence; `omi_stt_cost_routing_emission_ack_errors_total`
counts missing acknowledgements or exceptions, and
`omi_stt_cost_routing_votes_total{target,scope,result}` explains gate admission.
`omi_stt_cost_routing_canary_outcome_total{arm,outcome}` captures the actual router
allocation before initialization, including failed/fail-open sessions. No
UID/content labels are added.
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
provides no evidence of language-state leakage into that gauge. Every v6
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

### Historical aggregate shadow replay (v4, 2026-10-02)

This earlier v4 counterfactual is retained as context, not v6 qualification.
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
