# Modulate serve-error deaths: type, severity, and the selection circuit

Incident window: 2026-08-31 → 09-01 (backend-listen, Loop S sensor).
`ERROR:utils.stt.streaming:Modulate streaming error: Internal server error`
was the #3 error signature (×11/30m), with `Unable to complete the request.
Please try again.` at #10 (×5/30m); the sensor logged 62 more over the
following 6 hours. Modulate-Velma-2 is the streaming **primary**
(`modulate-velma-2,soniox,dg-nova-3,parakeet`), so during such an outage
every new session is handed to Velma, serves briefly, takes the error frame
mid-session, and fails over.

## What was broken

The sessions **survived** — mid-session failover (#12459) moved each one to
Soniox/Deepgram — and that survival was exactly why nothing else reacted:

- `SafeModulateSocket` latched the death but **no typed reason** (only the
  Soniox socket had a `typed_death_reason` latch), so the failover seam's
  `note_typed_provider_death` read `None` and returned False:
  `_modulate_circuit` never opened.
- The rescued session never runs `terminate_live_stt_session` — the other
  funnel that feeds the circuit.
- The next session's successful *connect* calls `record_success` and resets
  the connect-time failure counter, so the threshold can never trip under
  reconnect load either. This is the precise blindness
  `ProviderCircuitBreaker.record_serve_failure` was built for — leaking at
  the one seam that observes these deaths.

Net effect: provider selection re-chose the failing primary for every
reconnecting client for the duration of each outage, burning dead-stream
latency and one dropped segment per failover, while a healthy chain sat
configured right behind it.

## The fix (mirror of the Soniox 402 precedent)

| Frame (free text) | Typed reason | Severity | Bench? |
|---|---|---|---|
| `Internal server error` | `modulate_serve_error` | **ERROR** | yes — one cooldown window |
| `Unable to complete the request…` | `modulate_serve_error` | **ERROR** | yes |
| `Monthly usage limit reached.` | `modulate_serve_error` | **ERROR** | yes |
| `Invalid input audio` | untyped | WARNING | no — our/client fault |
| `rate limit`, unknown wordings | untyped | WARNING | no — session-scoped |

- `modulate_death_reason()` (utils/stt/streaming.py) bounds the provider's
  free-text frame to `MODULATE_DEATH_SERVE_ERROR` for server-fault shapes
  only; everything else degrades to untyped rather than growing the bounded
  vocabulary per provider wording.
- The socket latches the typed reason next to the raw text on the death
  latch; severity follows fault origin at the frame (serve error stays ERROR
  — it IS the outage signal).
- `modulate_serve_error` joins `_KNOWN_FAILURE_REASONS` (phase
  `connection`) and `_CIRCUIT_OPENING_REASONS`, so both the failover seam
  (`note_typed_provider_death`) and the terminal funnel
  (`terminate_live_stt_session`) open `_modulate_circuit`.
- Recovery is unchanged: one `record_serve_failure` opens the circuit for
  one cooldown window (default 30s, `MODULATE_CIRCUIT_COOLDOWN_SECONDS`);
  the half-open probe restores Velma as soon as one stream serves again.
  Sessions already running fail over as before — close codes, client-visible
  events, and the fallback chain are untouched.

## Signals after the fix

- A real Velma outage still logs `ERROR … Modulate streaming error: Internal
  server error` — once per dying session, as the outage signal.
- The follow-on log line is new:
  `WARNING … Opening modulate selection circuit after serve-time death
  reason=modulate_serve_error`, and `stt_selection` fallback telemetry gains
  `reason=modulate_serve_error` (it previously classified the death as
  `provider_5xx` only at connect time, if at all).
- Terminal client events may carry `reason=modulate_serve_error` instead of
  the generic `connection_lost` (bounded vocabulary, no provider text).
