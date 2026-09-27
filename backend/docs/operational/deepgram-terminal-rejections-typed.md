# Deepgram terminal connection rejections — typed, single-shot, failover-ready

Date: 2026-09-18 · Scope: `utils/stt/streaming.py`
(`_deepgram_options`, `connect_to_deepgram`,
`connect_to_deepgram_with_backoff`, `connect_stt_socket_with_fallback`),
`routers/listen/receiver.py` (Deepgram primary comment) · Guard tests:
`tests/unit/test_deepgram_terminal_rejection.py`

Failure-Class: FC-typed-failure-collapsed-to-generic

## What happened

The backend-listen error feed carried this cluster, sustained for 12+ hours
(2026-09-18, ~4.2k lines / 30m combined):

```
ERROR:utils.stt.streaming:Deepgram connection start() returned False — connection not established
ERROR:deepgram.clients.common.v1.abstract_sync_websocket:WebSocketException in AbstractSyncWebSocketClient.start: server rejected WebSocket connection: HTTP 402
ERROR:deepgram.clients.common.v1.abstract_sync_websocket:WebSocketException in ListenWebSocketClient.start: server rejected WebSocket connection: HTTP 402
ERROR:utils.stt.streaming:Deepgram start() returned False on all 3 attempts — giving up
```

The arithmetic (1469 ≈ 3 × 490) said it outright: the SDK was answering every
upgrade with a deterministic HTTP 402, and the backend retried that answer
three times per session while logging it under four signatures, none of which
is a `Deepgram` status the on-call could route on. Every affected session also
paid the full backoff ladder before its fallback chain was consulted.

## What was broken (three defects, one incident)

1. **The SDK option was a string.** `_deepgram_options` set
   `termination_exception_connect="true"`. deepgram-sdk 4.8.1 checks that
   option twice per connect with two different semantics: the shared websocket
   base class tests truthiness (`options.get(..., False)`) so the string
   passes there and the exception re-raises (the first SDK ERROR line), but
   `ListenWebSocketClient.start` — the wrapper that actually serves sessions —
   re-tests with an identity comparison (`... is True`), so the string fails
   and the same exception is swallowed back into `start() is False` (the
   second SDK ERROR line). Reproduced locally against the real SDK classes:
   with the string, `start()` returns `False`; with the boolean, the
   `InvalidStatus` propagates.
2. **A `False` start was retryable.** `connect_to_deepgram` maps a `False`
   start to `None`, and `connect_to_deepgram_with_backoff` retries `None`
   three times — correct for transient failures, pure waste for an
   account-state refusal no retry can change.
3. **The fallback helper bucketed the result as `provider_5xx`.** Whatever
   emerged from the Deepgram chain entered
   `connect_stt_socket_with_fallback`'s generic `except Exception`, so
   `stt_selection` fallback telemetry recorded `reason='provider_5xx'` for
   what was actually an auth/billing refusal — the true cause was only
   recoverable from the raw SDK error lines.

## The fix

- The option value is the boolean `True`, with the SDK's two-check contract
  documented at the option (an identity-checked boolean, not a truthy string).
- New typed `DeepgramConnectionRejection(RuntimeError)` carrying
  `status_code`, raised by `connect_to_deepgram` for terminal
  account-state rejections (401 invalid key, 402 billing, 403 forbidden) via
  `deepgram_rejection_status()`; 429/timeouts/5xx deliberately stay retryable.
- The backoff loop treats that type as terminal: one ERROR line, immediate
  raise — no ladder. Every pre-existing behavior for retryable inputs
  (`None`, exceptions, `is_active` aborts) is unchanged and pinned by tests.
- The fallback helper has a typed arm recording `reason='auth'` (the existing
  telemetry vocabulary for account-state refusals) and still counts the
  circuit failure, so the provider keeps its 30s breather at threshold.
- The receiver's Deepgram primary comment records why the no-modulate
  short-circuit branch now raises after one attempt (the typed error replaces
  the exhaustion raise there; `initialize_stt`'s terminal path handles both
  identically — the session is closed cleanly with
  `reason='initialization_failed'` either way).

## Operator-visible after this lands

- The `start() returned False` family disappears for account refusals; one
  `Deepgram connect rejected terminally after 1 attempt(s): ... HTTP 402`
  line per session replaces the three-line triple.
- A dead Deepgram account now costs at most one connect per process per
  cooldown window (circuit) instead of three per session, and sessions
  fail over to Modulate/Parakeet one backoff ladder earlier.
- `stt_selection` fallback records carry `reason='auth'` during account
  incidents — queryable directly, no raw-log archaeology.
- Rate limits (429) and outages (timeouts, 5xx) behave exactly as before.

## Regression coverage

`tests/unit/test_deepgram_terminal_rejection.py`:

- The SDK contract itself, through the real client classes with the socket
  connect faked: string → `start() is False` (the swallow), boolean → typed
  raise; the option pinned by identity (`is True`) across hosted,
  self-hosted, BYOK, and both managed construction paths.
- Classifier table: 401/402/403 terminal; 429/503/timeout/plain WebSocket
  failures/missing or non-int status not; legacy `InvalidStatusCode` shape
  covered; the terminal set pinned to exactly `{401, 402, 403}`.
- Backoff budget: refusal raises after exactly 1 attempt with no sleep (and
  one log line); `None` still exhausts to `None` after 3; transient failures
  still walk the full ladder and still recover on a later attempt; a refusal
  mid-ladder short-circuits the remaining retries; the pre-attempt
  `is_active` guard is untouched; the typed class crosses the real
  `run_blocking` seam; `process_audio_dg` propagates it.
- Fallback chain: refusal → `reason='auth'` + circuit failure; the leg AFTER
  the refusal carries `auth` forward (not `provider_5xx`); chain opens the
  Deepgram circuit at threshold, shields the account from a second refusal
  while open, recovers on a healthy connect after cooldown, and never opens
  Parakeet's circuit.
- Receiver: refusal on a language Modulate cannot serve terminates after one
  attempt without touching Modulate; refusal on a Modulate-capable session
  still reaches Parakeet through the full chain.
- Fails-on-parent evidence: the file fails collection on the pristine parent
  (typed name absent); reverting only the option value fails 5 tests
  including the real-SDK swallow pin; removing only the backoff typed arm
  re-engages the retry ladder (the behavioral refusal tests fail by timeout
  against real backoff sleeps).
