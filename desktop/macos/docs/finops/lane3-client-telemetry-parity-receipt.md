# Lane 3 client telemetry parity receipt

Status: fixture parity only. Live canary acceptance is pending. Lane 4 voice-panel parity and fallback-triage parity are pending. Do not retire `desktop_health_event`.

Flags `client_telemetry_transport_shadow` and `client_telemetry_posthog_retirement` default off. The retirement flag does not stop PostHog infrastructure events in this lane. Non-release bundles do not invent a `production` or `beta` channel.

## What this lane proves

Deterministic fixture `docs/finops/lane3-parity-fixture.json`, checked by `DesktopDiagnosticsManagerTests.testLane3ParityFixtureMatchesVoiceFallbackAndScreenPopulations` and `ScreenTaskPipelineTests.testScreenTaskTerminalsKeepExactDenominatorsAndDoNotRewriteEarlierFrames`.

- Physical shortcut and floating voice stay separate. Successful terminals are the only latency observations. Excluded and failed turns keep their outcome and omit latency.
- Fallback counts are exact for `recovered`, `degraded`, and `exhausted`, with areas `realtime_hub`, `screen_task_gate`, and `ptt_cascade`. Unregistered from/to/reason values become `unknown` on the shadow observation. PostHog still buckets unknown areas and reasons with its existing rules.
- Three screen-task terminals: eligible-frame sum 3, one `gate_rejected`, one pre-upload failure (`failed`, no extraction or legacy attempt, `extractor=none`). Stage duration `0` stays on the observation and does not enter the histogram. A later pending-delivery value does not rewrite the earlier terminal.
- macOS `Device Disconnected` is unchanged and stays on PostHog for connection balance.
- `desktop_health_event` still records physical `voice_turn_started`, `voice_turn_terminal`, and `fallback_triggered`.

## Transport covered in unit tests

Owner-scoped outbox, frozen event ids across retry and restart, overflow by count and bytes, logout/account swap without reattribution, one same-owner 401 refresh, no send under the other owner's token, 422/409 drops, five-attempt exhaustion, Retry-After honored up to 300 seconds and parked above that, stale observations dropped before send. Request body has no owner id.

## Still pending before any switch

- Seven closed UTC canary days, volume floors, and the 1% / latency gates in the frozen contract.
- Lane 1 must accept these attribute literals, including shadow `unknown` from/to values and the screen-task v2 strings.
- Lane 4 rendered voice panel and fallback triage against this fixture. Backend aggregates alone do not prove those consumers.
- Parent activation of the shadow flag. This lane does not enable it.
