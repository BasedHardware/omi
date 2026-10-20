# listen-edge (D1: passthrough, not deployed)

Rust websocket edge that will sit in front of `backend-listen` (plan D, realtime
gateway). In D1 it only relays: it accepts `/v4/listen`, opens the same path and
query on the upstream listen service with the client's headers, and relays every
text and binary message in both directions. It decodes nothing and opens no
provider legs. No image, chart or deploy references it yet.

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

Drain finishes within ready delay + spread + close timeout + 3s (23s by default:
one second each for a session's own abort close, the final flush, and
scheduling). The pod's `terminationGracePeriodSeconds` must exceed that. The
toolchain is pinned in `rust-toolchain.toml` and in CI.

## Metrics

Every label value comes from a closed enum, and every series exists from
startup (see `src/metrics.rs`; a unit test enforces the enum set and a 120-series
budget). There are no uid, session, path or peer labels.

`omi_edge_sessions_active`, `omi_edge_sessions_total{outcome}`,
`omi_edge_handshakes_total{result}`, `omi_edge_frames_total{direction,kind}`,
`omi_edge_bytes_total{direction}`, `omi_edge_frames_discarded_total{direction}`,
`omi_edge_upstream_connect_seconds`, `omi_edge_session_seconds`,
`omi_edge_draining`, `omi_edge_build_info{release_sha}`.

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
