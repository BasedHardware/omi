# Modulate serve-error bench: escalation and serving-evidence re-close

Incident window: 2026-09-20 → 09-22 (backend-listen, Loop S sensor). The
Velma-2 primary spent hours dying mid-session —
`ERROR:utils.stt.streaming:Modulate streaming error: Internal server error`
at ~1.2-3.3k lines per hour (~12k on 09-20, ~33k on 09-21) — while every
session was rescued by mid-session failover. This is the successor incident
to the 2026-08-31 storm (see `modulate-serve-error-deaths.md`): the typed
death, the ERROR severity, and the selection-circuit opening from that fix
all worked. What leaked was the **recovery side** of the circuit.

## What was broken

The serve-error bench opened for a flat 180s
(`MODULATE_SERVE_ERROR_CIRCUIT_COOLDOWN_SECONDS`), then recovery re-closed
the breaker on three "successes" whose only evidence was the **0.3s
post-connect liveness grace** (`fallback_socket_is_serving`). A provider
fault that kills streams mid-session strikes long after 0.3s, so the very
first probe after every window passed the grace, its connect-time
`record_success()` re-closed the breaker completely, and selection re-admitted
the failing primary at full session rate. Under reconnect load the whole
admit → serve → die → fail-over → re-admit cycle repeated about every three
minutes for the length of the outage — measured 2026-09-22: 194
`Opening modulate selection circuit` records in the single minute after the
outage ended (the backlog of deaths the cycle had been producing), plus a
sustained ~500 mid-session failovers per 10 minutes against a healthy
Deepgram/Parakeet chain.

Prod evidence shape (backend-listen, 2026-09-22): Velma serve-error ERROR
lines at ~50/minute for hours, while `record_serve_failure` had re-armed
every ~3 minutes; when the provider recovered at 08:12Z the death backlog
drained and circuit-open records clustered in one minute. A flat bench with
liveness-only re-close cannot reduce exposure during exactly the incidents
the bench exists for.

## The fix

Two coordinated changes to `ProviderCircuitBreaker`
(utils/stt/provider_resilience.py), both scoped to benches raised by
serve-time deaths; connect-time benches keep the historical 30s window and
close-on-first-success:

1. **Escalating bench.** Each `record_serve_failure` within an unbroken
   benching cycle doubles the next window — 180s → 360s → 720s → 1440s cap
   (`serve_bench_seconds`, cap at 3 escalation events). The cap is what keeps
   the provider probeable: even at the top of the ladder a still-unhealthy
   provider is re-probed roughly every 24 minutes, and a full close (real
   recovery) resets the ladder to baseline for the next outage.
2. **Serving-evidence re-close.** While a serve-error bench stands in
   half-open, a probe's connect-time `record_success()` no longer
   contributes toward closing the breaker; only `record_success(serving=True)`
   — real serving evidence, fired by the probe socket's first transcript
   segment (`_handle_utterance`) or the provider's `done` frame — counts the
   `MODULATE_SERVE_ERROR_SUCCESSES_TO_CLOSE` (3) consecutive successes and
   closes the breaker. `SafeModulateSocket.set_health_callbacks` is the
   seam (same shape the windowed-parakeet socket already uses), attached by
   `connect_stt_socket_with_fallback` when the primary is Modulate and the
   circuit admitted it half-open.

Net effect during an outage: exposure shrinks from ~1 cycle per 3 minutes
to ~1 probe every 6, 12, then 24 minutes, and each probe's own death
immediately re-arms the next (longer) window — a doomed probe can no longer
unlock the gate for everyone behind it. When the provider genuinely
recovers, the first probe that actually transcribes closes the breaker and
the ladder resets, so recovery is adopted on the first evidence, not the
third window.

## Signal changes

- `Opening <provider> selection circuit after serve-time death` now carries
  `bench_seconds=<n>` so the escalation ladder is visible in logs instead of
  a flat repeating record.
- `stt_selection` fallback telemetry: `outcome='recovered'` for Modulate
  primaries now means a probe actually served (transcript or done), not
  merely survived 0.3s; the surviving-session accounting is unchanged.
- No client-visible change: sessions already running fail over exactly as
  before; only selection's re-admission pacing changes.

## Tunables

- `MODULATE_SERVE_ERROR_CIRCUIT_COOLDOWN_SECONDS` (default 180) — the
  baseline rung of the ladder.
- `MODULATE_SERVE_ERROR_SUCCESSES_TO_CLOSE` (default 3) — consecutive
  serving-evidence successes that close the breaker.
- The escalation ladder (2x per event, cap 3 events) is code, not env:
  it bounds worst-case exposure without adding a knob nobody can observe
  misconfigured in prod.

Failure-Class: FC-typed-failure-collapsed-to-generic — the same class the
2026-08-31 fix closed: a typed provider answer (here, repeated typed
serve-error deaths) collapsed by the recovery path into a generic
"success" that kept re-admitting the failing provider, so the same
exhausted failure kept firing. The tail clause of the class is the
contract this closes: a refusal/evidence signal the caller already holds
must keep its class into the recovery decision, not be re-folded at the
boundary that needs it most.
