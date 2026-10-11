# Resilient live STT stream

The listen receiver already serializes mid-session provider failover. The managed
chain creates fresh provider callbacks and capture-position epochs; VAD admission
and the capture timeline record which decoded PCM was accepted by each socket.
Today a dead socket moves to the next provider, but audio accepted just before
death is not sent again. A Soniox `413 max_duration_reached` therefore acts like
an outage even though a fresh Soniox socket can continue the session.

`STT_RESILIENT_RECONNECT` defaults to `false` in every environment. When enabled,
single-channel server-STT sessions keep at most 15 seconds of outbound PCM in a
session-local memory ring. The ring is never persisted or logged, is trimmed at
the last capture-positioned finalized segment, and is cleared during finish or
drain. Soniox rotation, typed 5xx, and network send/receive deaths try one new
Soniox socket before the existing chain failover. Account, auth, invalid-hint,
idle, local queue, and other deaths follow the existing path. A failed reconnect
also returns to that path. The same socket factory and capture-position mapping
can later be used by a Parakeet leg without changing the provider interface.

Replay sends only retained audio after the last finalized capture sample, using
the original capture sample positions. A fresh provider epoch maps its new
relative timestamps back to those samples. Final segments whose capture end is
at or before the previous finalized position are discarded, so a replayed
prefix cannot appear twice. If an utterance exceeds the 15-second ring, its
oldest unfinalized audio is unavailable; recovery remains bounded and can have
a gap. No text or audio is used as a metric label.

The session allows at most three reconnect attempts, two in any rolling minute,
and 30 seconds of extra replayed audio. Once a limit is reached, the existing
provider chain handles the death. `omi_stt_reconnect_total` counts bounded
attempts and outcomes by provider and reason; `omi_stt_replay_seconds_total`
counts replay cost by provider. These are socket recovery signals. Transcript
language and correctness still require the separate output-language metrics;
a connected socket alone is not proof of healthy transcription.
