# listen-edge (D1 passthrough, D2 shadow; not deployed)

Rust websocket edge that will sit in front of `backend-listen` (plan D, realtime
gateway). In D1 it only relays: it accepts `/v4/listen`, opens the same path and
query on the upstream listen service with the client's headers, and relays every
text and binary message in both directions. D2 adds a shadow ingest
(`/v1/shadow`, below) where listen mirrors a cohort's raw frames and the edge
runs decode and VAD only. It opens no provider legs. No image, chart or deploy
references it yet.

Behaviour:

- **Handshake.** The upstream handshake runs before the client's 101, so a
  rejection from listen (for example 403 on bad auth) reaches the client with the
  same status and body. If upstream is unreachable the client gets 502, and 504
  on timeout. Hop-by-hop and handshake headers are regenerated; everything else
  is forwarded, and the peer is appended to `X-Forwarded-For`.
- **Messages.** Relayed in order, payload bytes unchanged. Pings are answered
  per hop. Close frames (code and reason) are relayed both ways. A side that
  vanishes without a close frame is mirrored as a drop to the other side.
- **Drain (SIGTERM).** `/readyz` turns 503 at once. New sockets are still
  accepted for `EDGE_DRAIN_READY_DELAY_MS`, and then the listener closes. Each open
  session gets close 1012 at a per-session offset within `EDGE_DRAIN_SPREAD_MS`.
  Frames the client sent before it saw that close are still relayed. Listen
  then gets **1001** (going away), whether the client echoes the 1012 or
  vanishes. Listen treats only 1000 and 1001 as ordinary closes, and only 1000
  finalizes a desktop conversation, so 1001 keeps the conversation in progress
  for the reconnect, as with a dropped client today. A client that stops reading
  cannot stall the drain: each close is bounded by `EDGE_CLOSE_TIMEOUT_MS`.
  Connections still in their upstream handshake when the listener closes are
  waited for and drained the same way.
- **Load shedding.** Upgrades beyond `EDGE_MAX_SESSIONS` open sessions or
  `EDGE_MAX_PENDING_HANDSHAKES` concurrent upstream handshakes get 503 with
  `Retry-After: 1`, before any upstream work. Request headers must arrive
  within `EDGE_HEADER_READ_TIMEOUT_MS`.

## Configuration

| Env | Default | Meaning |
|---|---|---|
| `EDGE_UPSTREAM_URL` | required | `ws://host:port` of backend-listen (no path) |
| `EDGE_LISTEN_ADDR` | `0.0.0.0:8080` | websocket, `/healthz`, `/readyz`, `/metrics` |
| `EDGE_PROXY_PATHS` | `/v4/listen` | comma-separated relayed paths |
| `EDGE_UPSTREAM_CONNECT_TIMEOUT_MS` | `5000` | upstream connect and handshake |
| `EDGE_DRAIN_READY_DELAY_MS` | `5000` | not-ready but accepting, after SIGTERM |
| `EDGE_DRAIN_SPREAD_MS` | `10000` | spread of 1012 closes across sessions |
| `EDGE_CLOSE_TIMEOUT_MS` | `5000` | close handshake limit per session |
| `EDGE_WS_READ_BUFFER_BYTES` | `4096` | per-socket read buffer |
| `EDGE_WS_MAX_MESSAGE_BYTES` | `16777216` | same as uvicorn's `ws_max_size` |
| `EDGE_MAX_SESSIONS` | `5000` | open sessions before new upgrades get 503 |
| `EDGE_MAX_PENDING_HANDSHAKES` | `512` | concurrent upstream handshakes before 503 |
| `EDGE_HEADER_READ_TIMEOUT_MS` | `10000` | time allowed for request headers |
| `EDGE_WORKER_THREADS` | CPUs | tokio worker threads |
| `EDGE_LOG` | `info` | tracing filter; logs are JSON |
| `OMI_RELEASE_SHA` | unset | exported on `omi_edge_build_info` |
| `EDGE_VAD_MODEL_PATH` | unset | Silero VAD ONNX (listen's `backend/utils/stt/assets/silero_vad.onnx`); unset disables `/v1/shadow` (503) |
| `EDGE_SHADOW_MAX_SESSIONS` | `500` | open shadow sessions before new mirrors get 503 |
| `EDGE_SHADOW_TOKEN` | unset | when set, mirrors must send it as `x-edge-shadow-token` |
| `EDGE_SHADOW_WORKER_THREADS` | `2` | threads of the separate runtime that decodes and scores mirrors (keeps shadow CPU off the relay and health workers) |

Drain finishes within ready delay + spread + close timeout + 3s (23s by default:
one second each for a session's own abort close, the final flush, and
scheduling). The pod's `terminationGracePeriodSeconds` must exceed that. The
toolchain is pinned in `rust-toolchain.toml` and in CI.

## D2 shadow (`/v1/shadow`)

listen (`backend/utils/stt/edge_shadow.py`, `EDGE_SHADOW_PERCENT`) mirrors a
static uid-hash cohort: every decoded client frame (raw payload, capture start
sample, listen's decoded sample count) plus its own VAD gate's per-window
Silero probabilities and gate opens. The edge decodes the frames, runs a port
of listen's gate, and compares window by window. Nothing goes back to listen,
the client, or any provider. The wire protocol (v1) is documented in
`src/shadow.rs`.

- **Decode** (`src/codec.rs`): `opus` and `opus_fs320` (libopus, 120 ms
  capacity), `pcm16` passthrough, `pcm8` (`audioop.bias(-128)` +
  `lin2lin(1, 2)`). Not yet: `lc3` / `lc3_fs1030` and `aac` (listen does not
  mirror them).
- **Gate** (`src/gate.rs`, port of `VADStreamingGate`): listen's 30 ms STT
  buffer chunking; per-chunk linear resample to 16 kHz exactly as numpy does it
  (`linspace` + `interp`, truncating to int16); 512-sample windows with a 64-sample
  context through Silero v6 (`src/silero.rs`, `ort`, one intra/inter-op thread);
  a chunk is speech if any window's probability exceeds the threshold for the
  state at the chunk start (0.65); SILENCE/SPEECH/HANGOVER with a 300 ms
  pre-roll and the session's hangover (4000 ms standard, 300 ms window lane);
  the window lane scores a `SessionPcmGain` copy (peak AGC to 0.8, at most 4x).
- **Alignment**: the edge holds decoded PCM (up to 10 s) until listen's first
  gate announces its origin sample, then starts its own gate there with the same
  parameters, so window `k` covers the same samples on both sides. Later listen
  gates (failover replacements fed replayed audio) count as `not_comparable`.
- **Comparison stream**: one `shadow_session` JSON log line per session
  (hashed session key, codec, counts, agreement, max probability difference,
  open matches) and at most 5 `shadow_window_disagreement` lines per session,
  20 per second per process.
- **Offline**: `edge-shadow-replay <model> <stream>...` runs recorded mirror
  streams through the same `ShadowCore` and prints a JSON summary per stream.
  `backend/scripts/edge_shadow_goldens.py` records the streams from listen's
  real gate and checks the D2 gate; `backend/scripts/edge_shadow_gate.py`
  checks it over `/metrics` scrapes.

Goldens (2026-10-20, this Mac): 3 repo speech clips plus a 20.8 s local clip,
each between room-noise gaps, × 7 encodings (pcm16 8/16/48 kHz, pcm8 8 kHz,
opus_fs320 16 kHz, opus 16 kHz 60 ms, opus 48 kHz) × 2 gate profiles:
43,660 windows, **100.00%** agreement, max probability difference 1.8e-6,
129/129 gate opens on the same chunk. `tests/shadow.rs` replays three of those
streams in CI.

## Metrics

Every label value comes from a closed enum, and every series exists from
startup (see `src/metrics.rs`; a unit test enforces the enum set and a 200-series
budget). There are no uid, session, path or peer labels.

`omi_edge_sessions_active`, `omi_edge_sessions_total{outcome}`,
`omi_edge_handshakes_total{result}`, `omi_edge_frames_total{direction,kind}`,
`omi_edge_bytes_total{direction}`, `omi_edge_frames_discarded_total{direction}`,
`omi_edge_upstream_connect_seconds`, `omi_edge_session_seconds`,
`omi_edge_draining`, `omi_edge_build_info{release_sha}`.

Shadow: `omi_edge_shadow_sessions_active`, `omi_edge_shadow_sessions_total{outcome}`,
`omi_edge_shadow_handshakes_total{result}`, `omi_edge_shadow_frames_total{codec,result}`,
`omi_edge_shadow_audio_seconds_total{codec}`, `omi_edge_shadow_vad_windows_total{codec}`,
`omi_edge_shadow_window_compare_total{codec,variant,result}`,
`omi_edge_shadow_prob_abs_diff`, `omi_edge_shadow_gate_opens_total{result}`,
`omi_edge_shadow_gate_open_offset_seconds`,
`omi_edge_shadow_processing_seconds_total{stage}` (thread CPU time).

D2 gate (plan D): agreement = `agree_*` / (`agree_*` + `*_speech_only`) ≥ 99.5%;
gate-open offset p95 ≤ 32 ms; decode+VAD CPU per audio second ≤ 7.92 ms
(6.6 ms/s + 20%).

## Test

```bash
cd backend/edge
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
```

The integration tests (`tests/`) run the edge between a real websocket client and
`FakeListen` (`tests/common/mod.rs`), a stand-in for listen whose behaviour is
chosen per connection by query parameters: echo, flood, close with a code,
drop, reject, mute, and linger. They cover ordered lossless relay with 32
concurrent sessions, close codes in both directions, mirrored drops, handshake
rejection, header and query forwarding, close timeout, and drain with frames in
flight.
