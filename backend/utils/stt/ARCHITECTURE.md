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

Provider fallback is a connection-time decision. A dead live socket terminates
the client connection; reconnect creates a new speaker-provider epoch before
its provider-local labels enter the resumed conversation.

## Speaker boundaries

`speaker_embedding.py` owns enrolled voiceprint verification. Its `0.45`
threshold is not a clustering control. `speaker_clustering.py` owns the more
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
- `speech_profile.py` and `speaker_embedding.py` own voiceprint extraction and
  verification; they do not assign in-session cluster identities.
- `vad.py` and `vad_gate.py` own speech admission; `outcomes.py` owns bounded
  transcription failure values.

The Parakeet image cannot import this package through an undeclared deployment
boundary, so `backend/parakeet/speaker_math.py` mirrors the two clustering
defaults and bounded-nearest policy for that image. Tests pin both copies.
