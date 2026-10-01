# Omi BLE simulator

`tools/OmiSimulator/` is a **Rust Crepuscularity (GPUI) desktop app** that
simulates an Omi wearable as a local CoreBluetooth GATT peripheral, so the
React Native macOS app's discovery and connect flows can be exercised with
no physical device. Area guide:
[`tools/OmiSimulator/AGENTS.md`](../tools/OmiSimulator/AGENTS.md).

Crepuscularity (`https://crepuscularity.tsc.hk` / `tschk/crepuscularity`) is
the UI framework only — **not an Omi API base**. The simulator has no HTTP
backend at all; it is a peripheral plus a control panel.

## BLE contract (all in `src/ble.rs`)

- Advertised local name **`Omi Devkit`**, advertising the audio service UUID
  — the app's discovery filter.
- Audio service `19B10000-E8F2-537E-4F6C-D104768A1214`: audio-data
  characteristic (Notify; u16 LE packet counter + `0x00` + PCM16 LE
  payload) and audio-codec characteristic (Read; `[0]` = PCM16).
- Device Information `0x180A`: model "Omi Devkit", serial `OMI-SIM-0001`,
  firmware `sim-1.0.0`, hardware `mac-simulator`, manufacturer
  "Based Hardware".
- Battery `0x180F`/`0x2A19` (Read + Notify, default 87%, UI-adjustable).
- Features `19B10020-…`/`19B10021-…` (LE u32 mask `388`: button, LED, mic
  gain).
- Button service `23ba7924-…`/`23ba7925-…` (Notify) — matches
  `OmiButtonServiceUUID` in
  `react-native/macos/RnRuntime-macOS/OmiNativeModule.mm`.
- Settings service `19B10010-…`: LED `…11` (0–100), mic gain `…12` (0–8),
  charging `…13`; out-of-range writes are rejected.

While "Record" is toggled, `src/audio.rs` captures the default mic via
cpal, resamples to 8 kHz mono PCM16, and emits 320-byte notify frames
(best-effort; degrades gracefully without a mic).

## Running

```sh
tools/OmiSimulator/run-mac.sh   # Metal env → cargo build → cargo run
```

Then scan/connect from the RN macOS app. The first build compiles gpui from
git and is slow. macOS requires Bluetooth permission for the host terminal
and microphone permission for Record. `.cargo/config.toml` is gitignored
(see `config.toml.example` for local path patches). The crate has no tests
and is outside `bun run check` scope.
