# Seeded acceptance journeys (SCA-488 / C2)

Five canonical, executable UI-journey definitions for the Omi mobile app,
plus the typed semantic-control surface they (and agents) drive. One
executable definition per behavior — replaced duplicates are retired, not
forked. C4 (verification integration) consumes this runner; C5 (device
qualification) reuses the same definitions on hardware.

## Run

```bash
# Hermetic host lane (default): real production pages/providers/HTTP client
# against a loopback fixture backend; external I/O faked at declared seams.
bash integration_test/journeys/run_journeys.sh

# Repeat the deterministic first vertical five times (acceptance signal):
bash integration_test/journeys/run_journeys.sh --filter j2 --runs 5

# Simulator lane (real app on a booted simulator, C1 session harness):
bash integration_test/journeys/run_journeys.sh --lane simulator --device <UDID> --api-base http://127.0.0.1:<port>/
```

The runner executes every journey file, collects evidence receipts
(`OMI_JOURNEY_EVIDENCE_DIR`, default a temp dir), rejects zero-execution
results, retries only launch-infra failures (never executed test failures),
and exits nonzero on any failing run.

## The five journeys

| Id | File | Behavior proved | Negative variant(s) |
| --- | --- | --- | --- |
| j1 | `j1_seeded_conversation_detail_test.dart` | seeded record fetched through the real provider path and rendered in the real detail page, exact synthetic identity | wrong-owner session cannot read the seeded record |
| j2 | `j2_chat_send_assistant_reply_test.dart` | send through the real UI button → request reaches the server → distinct assistant-role reply through the real SSE API path → rendered | suppress-send, suppress-assistant-reply, wrong-owner-session |
| j3 | `j3_memory_create_edit_reload_test.dart` | create + edit through the production provider path; survives reload server-side under the owning uid | drop-memory-save |
| j4 | `j4_expired_session_recovery_test.dart` | transient failure → local-dev re-mint reaches the real custom-token endpoint; terminal failure → explicit session expiry + blocked requests | production-family profiles never silently re-mint |
| j5 | `j5_capture_interruption_reconnect_test.dart` | interruption persists recoverable audio (real temp files, process reconstruction); reconnect drains it exactly once — via the C3 `capture-scenario/v1` adapter | fail-capture-recovery |

Every negative run arms exactly one named fault and MUST fail with the
missing invariant named (`JourneyFault.invariant`) — proving the oracle can
reject wrong behavior, not just accept right behavior.

## Faults

`app/lib/services/dev_controls/journey_faults.dart` — each fault corrupts
one declared external-I/O boundary:

- `suppress-send`, `wrong-owner-session` — client HTTP egress chokepoint
  (`HttpPoolManager`); production behavior is untouched when the gate is
  not armed (and arming is impossible outside debug local-dev builds).
- `suppress-assistant-reply`, `drop-memory-save` — the loopback fixture
  backend closes the stream with no reply / fails the persistence write.
- `fail-capture-recovery` — the replay world's scripted upload boundary.

## Hermetic lane boundaries (what is real, what is faked)

| Boundary | Real | Faked at the seam |
| --- | --- | --- |
| HTTP client, SSE parser, controllers, UI | ✓ | — |
| Backend server | — | `support/fixture_backend.dart` (loopback) |
| Firebase token I/O | — | `AuthService.installLocalHarnessTokenGateway` (debug + local_dev gated; the full-stack simulator lane uses real FirebaseAuth against the Auth emulator) |
| Device identity headers | — | `PlatformManager.initializeForLocalHarness` |
| Capture external I/O (clock/transport/uploads/native host) | production objects ✓ | C3 replay world (`test/support/capture/`) |

The hermetic lane boots the real page widgets and providers — it does not
boot `main()`/Firebase; the simulator lane boots the full real app. Both
lanes execute the same journey definitions (`OMI_JOURNEY_LANE`).

## Semantic controls (agent surface)

`app/lib/services/dev_controls/semantic_controls.dart` extends the existing
debug Marionette surface — same transport (debug VM service), no new server
or framework. `ext.omi.controls.*` expose typed state (route, principal,
capture lifecycle with `activeRecordingId` as the authoritative recording
identity), bounded `wait_ready` polling, navigation through the production
MaterialPageRoute path, and fault arm/clear. Installed only when
`kDebugMode && local_dev && OMI_DEV_CONTROLS=1` (dart-define); inert in
production-family builds including production-flavor debug builds — pinned
by `test/unit/semantic_controls_guard_test.dart`.

## Evidence

Each run writes a session-evidence-v1-accounted receipt: honest counts
(`passed + failed + skipped == executed`), `zero-execution` never passes,
state before/after, timestamps, fault + invariant text, and the assertion
timeline. Agents may append narrative findings but cannot author machine
pass results — passes come only from executed test assertions.
