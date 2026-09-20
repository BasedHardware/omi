# Parakeet v3/stream — client disconnects are lifecycle, not server faults

Date: 2026-09-20 · Scope: `parakeet/main.py` (`stream_transcribe`) ·
Guard tests: `tests/unit/test_parakeet_stream_disconnect_lifecycle.py`

Failure-Class: FC-peer-close-aborts-owed-write

## What happened

The parakeet (self-hosted streaming ASR) container logged this error
sustained at ~26-42 lines per 30 minutes (Loop S sensor, 2026-09):

```
ERROR:main:v3/stream error: Cannot call "receive" once a disconnect message has been received.
```

Every mobile or desktop client that ended a listening session by closing its
socket — the normal way every client ends every session — produced one of
these lines. The shutdown path worked: finalization still ran and the lease
was released (the `finally` block owns that). What broke was the signal:
a routine client hang-up was classified and logged exactly like a server
fault, on the one container whose log stream is watched for GPU/service
health. Sustained at ~50-80/hour it is pure noise floor, and it trains
anyone reading the feed to dismiss `v3/stream error` lines — burying the
genuine failures the classifier exists to surface (a real stream
initialization failure still logs the same `v3/stream error` prefix).

## Root cause

`stream_transcribe` dispatched each received message on content only:

```python
if "bytes" in msg:
    ...
elif "text" in msg:
    ...
```

Starlette (ASGI) delivers a client hang-up as a normal message of type
`websocket.disconnect`. That message has neither `bytes` nor `text`, so the
dispatch dropped it, the loop re-armed `await websocket.receive()`, and
Starlette answered from `client_state == DISCONNECTED` with
`RuntimeError('Cannot call "receive" once a disconnect message has been
received.')` — a generic transport-lifecycle error, logged at ERROR as a
`v3/stream error`.

The repo already knows the correct shape: every other backend websocket
receive loop classifies the in-band disconnect message before content
dispatch — `routers/listen/receiver.py` (the v4/listen audio loop),
`routers/chat.py`, `routers/omni_relay.py`,
`utils/other/endpoints.py`, and even this repo's own stack-harness stub
`testing/listen_pusher_stack/parakeet_stub.py`. The real Parakeet service
handler was the one raw `receive()` loop left dispatching on content only,
so the model-facing transport and its stub disagreed about the protocol.

## The fix

`stream_transcribe` now checks `msg.get("type") == "websocket.disconnect"`
before the content dispatch and `break`s to the existing normal-exit path:
final flush → session cleanup → admission-lease release → metrics. The
`except WebSocketDisconnect` arm (the transport-level exception Starlette
raises for post-close receives and direct closes) is unchanged, so both
hang-up shapes — the in-band disconnect message and the raised exception —
end the session without an error log. Genuine faults keep their exact
previous behavior: `except Exception` logs `v3/stream error` and closes
1011 `stream_initialization_failed`, and finalization still runs on every
exit path (including a flush that fails mid-disconnect).

## Verification

- New suite `tests/unit/test_parakeet_stream_disconnect_lifecycle.py`
  (46 tests): on the parent commit exactly the 7 incident pins fail
  (no-server-fault-after-disconnect assertions plus the labeled static
  tripwire) — red-on-parent verified in a detached worktree at the base
  commit; on the fix all 46 pass.
- Lifecycle controls (green on both sides, they pin what must not change):
  admission arming (1013 allocation/`service_not_ready` rejections, 1011
  admission-unavailable), ready-handshake, audio relay order and segment
  shape, receive-idle timeout continuation, finalize path (flush →
  cleanup → lease release), fault separation (feed failure still closes
  1011 and logs one `v3/stream error`), teardown ordering, and gauge
  behavior.
- `bash backend/test.sh` full suite green (file-isolated runner,
  `BACKEND_FAST_UNIT_FAIL_SECONDS=1.0` CI parity).

## Agent guidance

When adding or touching a raw `websocket.receive()` loop anywhere in the
backend (or the parakeet subservice), classify the in-band
`websocket.disconnect` message before any content dispatch and exit the
loop as a normal lifecycle event. A client hang-up must reach the same
cleanup/finalization path as `finalize` — never the `except Exception`
fault arm. If a receive loop can legitimately observe a message with
neither `bytes` nor `text` and needs to keep running, say so in a comment;
silently dropping unknown frames is how this incident happened.
