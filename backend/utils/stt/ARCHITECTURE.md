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
changes cannot reuse another numbering space.

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
