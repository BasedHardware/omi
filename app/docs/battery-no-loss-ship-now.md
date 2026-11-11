# Battery savings without frame loss — 2026-10-07

GRADE: B. Implemented, committed phone CPU/allocation reductions and disabled the forbidden automatic pause. Whole-phone battery savings are unmeasured; this is not a demonstrated cure for the field battery incident. No firmware dependency or deployment claim.

Branch: `feat/battery-no-loss-ship-now`, started at `3c672ba046`. Rebased onto `f5e4a550b8` after INV-CAP-1 landed in #20879 during this session. That main revision still enabled the silence-pause reducer. This lane disables it rather than assuming a parallel fix has shipped.

## Binding boundary and firmware findings

[INV-CAP-1](../../product/invariants/pendant-audio-retention.md) was first read from the tiered-app worktree because the prescribed base did not contain it. The canonical main document was read again after it landed. Its statement and prohibitions are unchanged; this lane adds continued-delivery guards and path enforcement.

In [`transport.c`](../../omi/firmware/omi/src/lib/core/transport.c), `pusher` removes frames from the TX ring. A connected subscribed peer goes to `push_to_gatt`; only `!conn` goes to offline storage. A connected unsubscribed peer releases the connection reference and sleeps, with no storage write. `on_audio_tx_done` frees a BLE TX slot, not a phone application durability receipt. `push_to_gatt` retries a failed notification three times; its failure has no retention fallback in `pusher`. Firmware cannot prove safe background app suspension merely from subscription being present. These findings rule out deliberate unsubscription and treating controller acknowledgement as durable custody.

## Implemented mechanisms

| Mechanism | Behavior and preservation | Saving and evidence quality |
| --- | --- | --- |
| Disable silence pause | Do not arm the timer; queued timeout events have no effects. Every new live pendant frame still reaches WAL/socket. Startup recovers historical automatic-mute markers through the serialized owner. Explicit mute remains authoritative. | Preservation fix, not an energy saving. Test delivers 300 packets through the former 120s boundary and counts all 300 retained frames with uploads failing. Manual pause, legacy recovery, reconnect and sync-fence tests remain covered. |
| Memoize native ingress policy decoding | Cache only the parsed exact JSON string. Every notification still reads current defaults and checks the process mute latch. Changed, malformed, oversized, missing and same-revision-changed policies take the current admission path. Only the BLE ingress owner uses the decoder; phone/batch writers keep uncached admission checks. | Mac benchmark: 100,000 real policy loads, 0.774303s uncached versus 0.081887s cached, about 89.4% less measured time in this operation. Behavioral test observes one parse across 10,000 unchanged loads and immediate denial on policy/latch changes. No timer, notification or frame is skipped. |
| Share owned BLE payload | Keep the ingress snapshot, strip its header once, and share the headerless payload among WAL, socket and voice-command buffering. Other source types retain their existing paths. | Removes one redundant payload allocation/copy per connected live BLE packet, and another during voice commands. Source evidence: [`BleDeviceSource`](../lib/services/audio_sources/ble_device_source.dart) and [`streamAudioToWs`](../lib/services/capture/capture_controller.dart). Regression mutates the producer's input after delivery and verifies unchanged socket bytes and the fsynced WAL golden. No claimed watt reduction. |
| Encode pendant WALs into one byte buffer | Preserve little-endian length prefixes, frame boundaries, bytes, index semantics, storage admission and flush deadlines. The non-pendant serializer is extracted unchanged. No socket/WAL coupling or delayed drain. | Five-round Mac benchmark median: 2.364146s legacy versus 0.267065s sized-buffer encoding for 1,000 chunks of 1,000 × 80-byte frames; about 88.7% less measured encoding time. Every output byte matches. This fixture is not an observed firmware packet-size distribution. |

Benchmark host: arm64 macOS, Dart 3.12.2 from mise Flutter 3.44.5, Swift 6.4. CPU microbenchmarks exclude physical iPhone power, radio behavior and filesystem write energy. Reproduction:

```sh
cd app
OMI_POLICY_BENCHMARK=1 ruby ios/test/batch_audio_energy_test.rb
dart run tool/benchmark_wal_frame_encoding.dart
```

The native benchmark is part of [`batch_audio_energy_test.swift`](../ios/test/batch_audio_energy_test.swift); the WAL reference is pinned in [`benchmark_wal_frame_encoding.dart`](../tool/benchmark_wal_frame_encoding.dart) to the serializer at `3c672ba046`. Tests compile and run the production policy/writers, not a mirrored policy.

## Costs that remain and rejected proposals

The [August field report #11547](https://github.com/BasedHardware/omi/pull/11547) cited 51% battery share and 16h background on iPhone 15 Pro Max/CV1. Its [revert #11567](https://github.com/BasedHardware/omi/pull/11567) disproved the claimed iOS foreground-task audio-session cause and rejected reconnect backoff. [#20837](https://github.com/BasedHardware/omi/pull/20837) linked the later 42% share/16h53m report to #5491 and #11307 but supplied no BLE-versus-cellular power decomposition. Battery share and background duration are not per-component watt measurements. They cannot establish which component dominates.

- **Keep BLE subscribed, then drop arrivals or close the socket after transcript silence:** rejected. Dropping arrivals violates the captured-audio-survives boundary. Transcript silence cannot prove absent speech when STT fails. Socket closure also needs a retained capture destination and immediate resume detection; no new drop/gate path is introduced. WAL flushes stay active because a socket write does not prove transcription or server durability.
- **Socket reuse:** current `PureSocket.connect` already refuses duplicate connecting/connected attempts and fences retired attempts. No evidence supports adding a second reuse layer. Reconnect timing is unchanged.
- **Longer pings, background socket close or a server hold:** rejected for this lane. [`PureSocket`](../lib/services/sockets/pure_socket.dart) schedules a 20s protocol ping, while [`runtime._heartbeat`](../../backend/routers/listen/runtime.py) independently sends text pings every 10s and applies an activity timeout. Changing only the client interval leaves server traffic; deleting liveness checks risks stale sessions. ESTIMATE from configured intervals: 180 client protocol pings/hour and 360 server text pings/hour under uninterrupted scheduling. These are not measured radio wake counts or energy costs, especially during continuous audio upload. No reliable mWh/hour value was found for this app.
- **HTTP/2 or upload connection-pooling changes:** live capture is a persistent WebSocket, not per-frame HTTP requests. Batch/upload behavior remains unchanged.
- **Client VAD:** the [`audio/`](../lib/utils/audio/) utilities provide transcoding, not a production pendant silence detector. The cloud [VAD gate](../../backend/utils/stt/vad_gate.py) maintains pre-roll, hangover and timeline mappings. Moving it requires equivalent codec coverage, false-negative acceptance and preserved source-time mapping, plus a measured decode/detect budget. Potential silent-byte savings are not established watts or safe speech suppression; no heuristic is shipped.
- **BLE connection-interval/MTU/L2CAP duty cycling:** rejected. [Firmware README](../../omi/firmware/omi/README.md) records iOS CI restrictions. Apple's [connection-latency API](https://developer.apple.com/documentation/corebluetooth/cbperipheralmanager/setdesiredconnectionlatency(_:for:)?language=objc) belongs to the peripheral-manager role; Omi's phone is central. Apple's [L2CAP API](https://developer.apple.com/documentation/corebluetooth/cbperipheralmanagerdelegate/peripheralmanager(_:didpublishl2capchannel:error:)) requires a published peer channel. Firmware exposes GATT notifications, not a live audio L2CAP protocol. Notification-size limits do not let the phone rewrite pendant packetization without firmware support.
- **Live codec/bitrate negotiation:** firmware's [`config.h`](../../omi/firmware/omi/src/lib/core/config.h) selects its live Opus codec/bitrate at build time; its codec GATT characteristic is read-only. No verified phone-side bitrate negotiation exists.
- **Socket batching:** backend [`receive_data`](../../backend/routers/listen/receiver.py) decodes each binary message as one codec packet. Concatenating Opus packets would break that contract and capture-evidence control/frame pairing. Delaying separate messages adds volatile transport buffering without demonstrated radio savings; no such delay is shipped.
- **Live Activity / telemetry / charging-only timers:** the Live Activity 30s heartbeat maintains its 90s stale lease, native capture health maintains ingress evidence, and existing diagnostics metrics already stop sampling without an active foreground listener. No additional cadence change is justified here. Charging-only deferral must not delay capture durability or repair.

BLE notifications, Dart frame ingress, cellular/Wi-Fi audio upload, client/server pings, native health and the existing 10s pendant durability drain all remain. ESTIMATE: at 100 packets/s, one removed decode/copy per packet is 360,000 operations/hour; at 50/s it is 180,000. These illustrative cadences come from the firmware README and [`BleAudioCodec.getFramesPerSecond`](../lib/backend/schema/bt_device/bt_device.dart), not this user's measured notification rate. The host savings do not justify a whole-day battery percentage claim.

Apple's [energy/networking guide](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/EnergyGuide-iOS/EnergyandNetworking.html) and [cellular best practices](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/CellularBestPractices/BestPractices/BestPractices.html) support avoiding frequent small transactions. They do not supply a current-device energy constant for Omi's pings. A real power comparison must preserve audio acceptance and compare matched worn-pendant sessions with Wi-Fi/cellular, screen state, firmware and reconnect history controlled.

## Verification receipts

Final terminal outputs are in `/Volumes/Ephemeral/scratch/battery-no-loss-ship-now-verification/`.

- `flutter analyze`: 89 diagnostics, zero new; final production layout. The accepted log follows removal of a redundant import introduced during helper extraction.
- Targeted capture/presentation/encoding/durability/custody/WAL suite: 190 passed on the final production layout.
- `TZ=UTC bash test.sh --timeout 2m`: 4,813 passed / 14 skipped on the final production layout, exit zero (20m28s main run). The separate opt-in spine run passed 138 tests. This exceeds the supplied 4,791 / 14 bar. No new flake is being classified as pre-existing. Prototype runs with compilation errors or incomplete test I/O waits were discarded and corrected.
- Native production writer/policy tests: `1 runs, 2 assertions, 0 failures, 0 errors, 0 skips`.
- Native capture health: `1 runs, 2 assertions, 0 failures, 0 errors, 0 skips`.
- Native capture transaction: `1 runs, 14 assertions, 0 failures, 0 errors, 0 skips`.
- Capture-evidence dark-write targeted tests: 17 passed with `CAPTURE_EVIDENCE_V1_DARK_WRITE=true`.
- Swift parse, byte-equivalence benchmark and `git diff --check`: passed.
- `scripts/pr-preflight --suggest`, draft-body validation and `OMI_PR_BODY_FILE=… make preflight`: 33 checks passed. Make run: 248.63s; final draft-body validation: 803.54s. Body declares `Failure-Class: new`, INV-CAP-1 and INV-DATA-1. The history-dependent failure-class guard prints its shallow-history skip; no historical enforcement claim is made.

No spine oracle, generated localization or firmware file was edited. Local checks do not establish terminal GitHub CI, an installed binary, deployment or physical-device acceptance.

## Residual risk and lane record

The decoder relies on the BLE manager's existing main-queue confinement; the exact durable value and deny-only latch are rechecked on every read. Payload sharing relies on downstream readers treating owned audio bytes as input; tests cover producer reuse and durable bytes. Current firmware's TX errors and OS eviction have no newly proven retention fallback. This lane avoids introducing a power-policy loss path; it does not claim to repair every existing physical transport failure or reconstruct historical gaps.

The original-base lane includes the Grafana and desktop Gemini main commits brought in by rebase, plus #20879. Product edits are isolated by comparing to `f5e4a550b8`. Final complete `git log --oneline 3c672ba046..HEAD`, original-base and product-only diff stats, and exact final SHA are in `lane-git.log` in the receipt directory.
