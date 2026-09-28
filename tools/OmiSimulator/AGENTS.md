# OmiSimulator — Developer Guide

Rust Crepuscularity (GPUI) macOS app that simulates an Omi wearable as a
local CoreBluetooth GATT peripheral for the React Native app's
discovery/connect flows. Crepuscularity (`https://crepuscularity.tsc.hk` /
`tschk/crepuscularity`) is the **UI framework only** — this crate is not an
Omi API base; there is no HTTP backend at all. Topic doc:
[`../../docs/simulator.md`](../../docs/simulator.md).

## Layout

```
Cargo.toml        # omi-simulator; git-pinned crepuscularity-gpui + gpui-ce (font-kit)
run-mac.sh        # canonical launcher: Metal/Xcode env → cargo build → cargo run
src/main.rs       # GPUI window + control panel (battery, LED, mic gain, button, record)
src/ble.rs        # CoreBluetooth peripheral: services, UUIDs, sim state
src/audio.rs      # cpal mic → 8 kHz mono PCM16 → BLE notify frames (best-effort)
.cargo/config.toml.example  # optional local [patch] overrides (real file is gitignored)
```

## Run

```sh
tools/OmiSimulator/run-mac.sh     # or plain `cargo run` with a sane env
cargo build --release             # nothing special; no custom profiles
```

First build compiles gpui from git (slow). Keep `font-kit` enabled on the
gpui dependency or the window renders with no text.

## BLE contract (see `src/ble.rs`)

Advertises as **`Omi Devkit`** with the audio service
`19B10000-E8F2-537E-4F6C-D104768A1214` (the RN v5 discovery filter): audio
data (Notify; u16 LE counter + `0x00` + PCM16 LE) and codec (Read; `[0]` =
PCM16). Plus Device Information `0x180A`, Battery `0x180F`/`0x2A19`
(default 87%), Features mask `388` (`19B10020/21`), Button
`23ba7924/25` — matching `OmiButtonServiceUUID` in
`react-native/macos/RnRuntime-macOS/OmiNativeModule.mm` — and Settings
`19B10010–13` (LED 0–100, mic gain 0–8, charging; out-of-range writes
rejected).

## Gotchas

- macOS only in practice (CoreBluetooth peripheral + cpal). The host
  terminal needs Bluetooth permission; Record needs microphone permission
  and degrades silently without it.
- Pair with the RN macOS app by running the simulator, then scanning in the
  app. Nothing to commit from `.cargo/config.toml`.
- No Rust tests and outside `bun run check` scope — verify by connecting
  the real app.
