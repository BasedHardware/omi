# Replay Harness STT Wire-Fidelity Oracle

**LIFECYCLE: permanent** — a deterministic, advisory structural protocol test
for the Parakeet live-STT WebSocket client. Run it with:

```bash
npm run test:replay-stt-wire-fidelity
```

The oracle starts a loopback-only controlled fake upstream and drives the
production `process_audio_parakeet` client, `ParakeetWebSocketSocket` sender /
receiver, and the listen receiver's fallback and terminal-session paths. It
does not contact a provider, run a service probe, capture traffic, or use
recorded audio.

## Contract

The fake upstream proves only the following wire and terminal-state contracts:

1. the client waits for `{type: ready}` before forwarding PCM;
2. synthetic PCM-frame order, segment delivery order, and the `finalize` tail
   flush survive the real client/receiver path;
3. a controlled close `1013` with the documented `capacity_full` class selects
   Modulate exactly once during startup;
4. a controlled close `1011` during initialization takes the bounded
   `service_status(stt_failed)` then client-WebSocket `1011` failure path when
   the one startup fallback is unavailable; and
5. a clean provider close without a terminal completion latches the socket
   dead and uses that same terminal path without an in-session retry.

It intentionally does **not** establish provider conformance, production
endpoint behavior, transcript correctness, client compatibility, a release
gate, Phase 0B, or end-to-end capture fidelity.

## Data safety

The only audio is two generated zero-filled byte arrays. The fake emits
synthetic non-user segment bodies only long enough to exercise the production
receiver; they are not logged, returned, or persisted. The oracle's printed
evidence is restricted to endpoint path shape, close-code classes, event
ordering, callback schema keys, fallback count, and terminal-state outcomes.
