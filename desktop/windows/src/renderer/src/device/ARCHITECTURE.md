# Wearable device stack (Windows)

LIFECYCLE: permanent

Windows port of the macOS Bluetooth subsystem (`desktop/macos/Desktop/Sources/Bluetooth`,
`.../Audio`). It connects an Omi-family wearable over BLE, decodes its audio to 16 kHz mono
PCM, and streams that into the same transcription lane the laptop microphone uses.

## Where the code runs

The stack lives in a **hidden renderer window** (`#/device`, created by `main/deviceWindow.ts`)
for two reasons: Chromium exposes `navigator.bluetooth` only to renderers, and a wearable has
to keep streaming when every UI window is closed. UI windows never touch the device; they send
commands over the device bridge (`main/ipc/deviceBridge.ts`) and render the events that come
back. Main owns the Bluetooth chooser, the persisted pairing, and every WebSocket.

```
Settings DeviceTab ──cmd──▶ main (deviceBridge) ──cmd──▶ device window (DeviceController)
        ◀──event───────────────────────────────────────────────┘
                                                    │
        device: GATT notifications ──▶ connection ──▶ BleAudioService ──▶ DeviceListenSession
                                                              (PCM)          │ listenFeed
                                                                             ▼
                                                              main omiListen ──▶ /v4/listen
```

## Layers (bottom up)

| Directory | What it owns |
|---|---|
| `protocol/` | Device types, codec table, GATT UUID registry, advertisement detection. Pure data and pure functions; every value is verbatim from the mac source because it is a firmware contract. |
| `session/` | Concurrency primitives: `DeviceOperationBroker` (one operation per key, injectable-clock timeouts, exactly-one-terminal completion), `UncorrelatedOperationGate` (poisons an identity after a non-success terminal), `DeviceCommandQueue`, `DeviceAudioStreamController`, `BluetoothConnectionLeaseRegistry`, and `DeviceSessionCoordinator` (the phase machine). |
| `transport/` | `BleTransport` over a `BlePhysicalDriver` seam. Single-use per connection attempt, fenced by a session generation. |
| `connections/` | `BaseDeviceConnection` plus one client per family (Omi/OpenGlass, Bee, PLAUD, Limitless, Fieldy, Friend Pendant, Frame) and the factory that picks between them. |
| `audio/` | Decoders (Opus via WASM libopus, AAC via WebCodecs, PCM and mu-law in TypeScript, LC3 silence placeholder), `BleAudioProcessor` (framing plus the degradation ladder), `BleAudioService` (one session, per-family routing). |
| `lane/` | `DeviceListenSession`: the /v4/listen conversation lane, its reconnect policy, and the bridge transport that binds it to preload. |
| `deviceController.ts` | Turns bridge commands into sessions and device state into bridge events. |

## Rules that are not obvious from the code

- **Detection order is a contract.** `detectDeviceType` is first-match-wins in the mac order
  (Bee, PLAUD, Fieldy, Friend, Limitless, Omi, Frame). Reordering changes which family claims
  an ambiguous advertisement.
- **A poisoned identity is never reused.** BLE callbacks identify a characteristic or command
  id, not an attempt. Once an operation on a key terminates without success, a late callback
  for that key can no longer be attributed to anything, so the key stays poisoned until the
  session is torn down.
- **The wire codec never leaves this package.** Every family is decoded here and the lane
  always carries linear16, exactly like microphone audio.
- **Only one conversation socket per user.** Two `/v4/listen` sockets for one uid coalesce
  through a racy server-side pointer, so the lane refuses to open while the continuous
  microphone session holds the slot (`listenConversationActive`).
- **The zero-delay reconnect does not scan.** Scanning clears the cached platform handle the
  immediate retry depends on; only the delayed (15 s) retry rescans.

## Divergences from the macOS source

- **Read correlation.** CoreBluetooth delivers reads and notifications through one callback and
  demultiplexes them with the read gate. WebBluetooth resolves a read through its own promise,
  so here the gate instead suppresses the read's `characteristicvaluechanged` echo. A late
  post-timeout value is still dropped by the poisoned key, as on macOS.
- **GATT serialization.** Chromium rejects concurrent GATT operations on one device, so the
  physical driver serializes them. CoreBluetooth needs no such queue.
- **Frame device info.** The Swift source applies its hardcoded device info in both
  `updateDeviceInfo` and `prepareDeviceAfterConnect`; since `connect()` runs them in that order,
  the second application discards the DIS firmware read the first one performed. This port
  applies them only where the read survives.
- **LC3 is silence.** Neither platform ships liblc3, so Friend Pendant audio decodes to silence
  of the correct length, which keeps timing correct and marks the session partially supported.

## Testing

Everything except the WebBluetooth adapter is unit tested without Electron: `testing/fakes.ts`
provides a virtual-time clock and an in-memory transport, and each family's client is driven
through scripted GATT tables. The Opus decoder is exercised against real libopus rather than a
stub. Protocol constants are pinned by tests because they are firmware contracts, and the
suites are mutation-audited: seeded regressions in detection order, framing widths, the
degradation ladder, gate poisoning, reconnect budgets, and lane exclusion all fail the suite.
