# LC3 frame-cadence replay oracle

Run with:

```bash
npm run test:replay-lc3-frame-timing
```

This is a Linux x86_64-only, loopback-only test harness. It requires the
locked `lc3py==1.1.3` backend environment and rejects unsupported hosts rather
than skipping. A test-owned `lc3.Encoder` produces three inert in-memory
30-byte / 10 ms frames. The harness runs the production listen admission
format check and codec normalizer, the real `ListenReceiver` LC3 decoder, and
the real `ParakeetWebSocketSocket` against a local fake upstream.

The oracle proves that those frames decode to three 320-byte PCM frames and
flush one 960-byte STT message after frame three. When the fake upstream
closes, a fourth queued frame produces no second STT message or reconnect; the
listen client gets one bounded terminal status and closes with `1011`. A
test-only decoder-bypass mutant is required to fail the same decoded-size and
flush-index checks.

The emitted evidence is structural only: labels/order, byte-count buckets,
counts, close/retry enums, `10ms_frame` / `30ms_flush` timing buckets, hashes
of static metadata, and a coarse local deadline. It never emits, logs, hashes,
or persists audio bytes, audio-derived values, transcript text, IDs, headers,
credentials, provider bodies, or payload hashes. A default-deny egress guard
allows only the in-process loopback upstream.

Residual gaps: this does not qualify Flutter, Friend Pendant, device behavior,
multi-channel LC3, malformed or variable-length LC3 policy, provider quality,
real scheduling/finalization/reconnect timing, capture corpora, or production
network/release behavior. Existing Listen/Pusher and Sync/Cloud Tasks gauntlets
remain unchanged.
