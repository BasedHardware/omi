# Soniox in-stream rejections: keep the type, split the severity

Incident window: 2026-08-30/31 (backend-listen, Loop S sensor).
`ERROR:utils.stt.soniox:Soniox streaming error:` was the #4 error signature
(~52 events / 30 min) carrying three unrelated provider behaviors on one
free-text line:

| Frame | Typed reason | Owner | Severity |
|---|---|---|---|
| 400 `invalid_request` "No audio received" during an active session | `soniox_idle_timeout` | this session's VAD pattern | WARNING |
| 400 `invalid_request` "No audio received" after teardown starts | `soniox_no_audio_teardown` | clean session teardown | metric only; no failure/failover |
| 402 `organization_balance_exhausted` / `organization_monthly_budget_exhausted` / `project_monthly_budget_exhausted` | `provider_budget_exhausted` | the provider/account | **ERROR** |
| 413 `max_duration_reached` | `soniox_rotation` | documented protocol rotation | WARNING |

## What was broken

- Every in-stream error frame — including two shapes that are the protocol
  answering how the session was used — logged at ERROR, so a fleet of
  VAD-starved sockets was indistinguishable from a serving outage.
- The socket laundered the typed frame into free-text `death_reason`
  (`soniox error: 402 organization_balance_exhausted …`); every terminal funnel
  (`terminate_live_stt_session`, the death monitor, the send path) collapsed it
  to `connection_lost`, so `omi_live_stt_terminal_failures_total` carried no
  cause distinction.
- `_fallback_failure_reason` matched neither `exhausted` nor `balance`, filing
  the 402 as `provider_5xx` in fallback telemetry.
- `bounded_provider` did not know the live-path tokens `soniox` /
  `deepgram_cloud`, so terminal-failure metrics reported `provider='unknown'`.
- A 402 provider still **accepts connects** while refusing every stream:
  mid-session failover moved each dying session to the next provider and the
  session survived, so the terminal path that feeds the selection circuit never
  ran, and each new session was handed straight back to the refusing provider.

## The contract now

- `soniox_death_reason(error_code, error_type)` bounds the provider's own typed
  frame into the terminal vocabulary; unknown shapes degrade to
  `connection_lost` rather than growing per-message cardinality.
- The socket latches both the raw frame (`death_reason`, for logs) and the
  bounded type (`typed_death_reason`); `GatedSTTSocket` proxies the typed
  reason so the VAD gate cannot erase it.
- `live_stt_terminal_reason(socket, fallback)` lets every terminal funnel
  report the provider's type instead of its own vantage point.
- Severity follows fault ownership: a 402 / monthly-budget refusal stays at
  ERROR (`Soniox streaming error:`); idle-timeout and rotation log
  `Soniox stream closed:` at WARNING. Never mute a signature without
  classifying fault origin first — see `ws-auth-rejection-severity.md` for the
  same rule at the auth boundary. `organization_monthly_budget_exhausted`
  used to miss the typed set and log at WARNING as `connection_lost`.
- Fleet evidence: `note_typed_provider_death` at the failover seam (and
  `provider_budget_exhausted` in the terminal path) opens the provider's
  process-local selection circuit for one cooldown. Session-scoped reasons
  deliberately do not — an idle timeout is this session's VAD pattern, not a
  provider fault.
- Vendor close frames increment `omi_stt_stream_close_total` with a bounded
  `reason` (`provider_budget_exhausted`, idle/rotation/hint/teardown, else
  `connection_lost`). Raw vendor messages are never label values.
- The active-session idle rejection does not follow a keepalive gap in the
  current adapter: `_send_loop` sends a keepalive after each 10 seconds without
  queued audio, below Soniox's documented 20-second idle close. VAD starvation
  still remains visible as `soniox_idle_timeout`; keepalive is not audio.
- Teardown sends Soniox's empty end-of-audio frame only after at least one audio
  payload reached the provider. A zero-audio finish closes without that frame
  or a wait for `finished`; a teardown-phase no-audio rejection is counted as
  `soniox_no_audio_teardown` and is not latched as a socket death.
- `_fallback_failure_reason` classifies `exhausted`/`balance` text as `quota`;
  `bounded_provider` accepts the live-path provider tokens.

## Regression coverage

`tests/unit/test_soniox_typed_rejections.py` drives the real `SafeSonioxSocket`
receive loop over the exact prod frame shapes, the real `ListenReceiver`
failover and death-monitor paths, and the real terminal/send paths; only the
process-global circuit opener is patched.

Failure-Class: FC-typed-failure-collapsed-to-generic (instance fix; class
canonized by #11487 in the proactive lane — the same collapse at the live-STT
boundary).
