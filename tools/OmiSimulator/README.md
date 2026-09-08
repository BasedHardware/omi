# Omi Simulator (v5) — Crepuscularity / GPUI

Full **Rust** desktop simulator for local React Native v5 BLE discovery.

## What Crepuscularity is here

**Crepuscularity** ([https://crepuscularity.tsc.hk](https://crepuscularity.tsc.hk), repo [`tschk/crepuscularity`](https://github.com/tschk/crepuscularity)) is the **multi-target UI framework** (GPUI / web / native / SwiftUI View IR / etc).

In this tool it is wired as the **GPUI desktop UI shell** only — **not** an Omi API base URL, branding CDN, or firmware host.

BLE remains a **local CoreBluetooth GATT peripheral** (via [`ble-peripheral-rust`](https://crates.io/crates/ble-peripheral-rust) on Apple). There is **no HTTP backend**.

## Layout

```
tools/OmiSimulator/          ← Rust Crepuscularity GPUI app (this tree)
  Cargo.toml                 ← path dep → local crepuscularity checkout
  src/main.rs                ← Crepus view! UI
  src/ble.rs                 ← Omi Devkit peripheral (DIS/battery/features/button/settings/audio)
  src/audio.rs               ← cpal mic → 8 kHz PCM16 notify frames (best-effort)
tools/OmiSimulator-swift-legacy/  ← previous SwiftUI + CBPeripheralManager sim (reference)
```

Cargo prefers a **path** dependency on the local framework checkout:

`/Users/undivisible/projects/crepuscularity/crates/crepuscularity-gpui`

(also reachable as `/Users/undivisible/Projects/crepuscularity` on case-insensitive volumes).

## Build / run (macOS)

Do **not** overwrite `/Applications/Omi.app`. This binary is `omi-simulator` (`com.basedhardware.OmiSimulator`).

Metal / Xcode env (GPUI compiles Metal shaders):

```bash
eval "$(/Users/undivisible/projects/crepuscularity/scripts/metal-env.sh)"
# or:
export SDKROOT="$(xcrun --show-sdk-path)"
export DEVELOPER_DIR="$(xcode-select -p)"
export TOOLCHAINS=Metal
```

From this directory:

```bash
cd tools/OmiSimulator
cargo build
cargo run
```

Or from repo root:

```bash
cargo run --manifest-path tools/OmiSimulator/Cargo.toml
```

Grant **Bluetooth** (and **Microphone** if recording) when macOS prompts.

## How discovery works

RN v5 scans by the Omi **audio service UUID**:

`19B10000-E8F2-537E-4F6C-D104768A1214`

Advertised local name: **`Omi Devkit`**. On macOS, CoreBluetooth often ignores the advertisement local name and uses the Mac’s computer name — discovery still succeeds via the service UUID.

## GATT services

Same cut as the prior Swift sim:

| Service | Notes |
|---------|--------|
| DIS `180A` | model Omi Devkit, fw sim-1.0.0, hw mac-simulator, mfr Based Hardware, serial OMI-SIM-0001 |
| Battery `180F` | level read+notify (default 87%); UI ±5 |
| Features `19B10020-…` | bitmask **388** (button+LED+mic) |
| Button `23ba7924-…` | notify; UI **Double press** → `[2,0,0,0,0,0,0,0]` |
| Settings `19B10010-…` | LED / mic gain R/W; charging R+notify |
| Audio `19B10000-…` | notify frames + codec `0` (PCM16) |

## Gaps vs old Swift-only sim

- UI is Crepuscularity `view!` (buttons for battery ±5 / charging toggle) rather than SwiftUI `Slider`/`Toggle`.
- Mic path uses **cpal** (best-effort). If no input device or format mismatch, Record still toggles but may not stream.
- App is a **Cargo / GPUI** process, not an `.xcodeproj` / `.app` bundle. TCC Bluetooth/Mic prompts still apply; unsigned `cargo run` binaries can be blocked until Max allows Bluetooth for the terminal/host process.
- Haptic + Storage services still omitted (same as Swift cut).
- Same-Mac advertised local-name quirk unchanged.

## Verify from the RN app

1. Start this simulator (`cargo run` in `tools/OmiSimulator`).
2. In RN v5 on Android or macOS, start a BLE scan.
3. Connect — expect DIS / battery / features=388 / settings / button double-press.


## Mac dependency pins (gpui-ce)

`crepuscularity-gpui` normally depends on `gpui` / `gpui_platform` from
`https://github.com/gpui-ce/gpui-ce`. Tip currently has a broken
`crates/gpui_ce_components` gitlink (no `.gitmodules` URL), which breaks
`cargo update` of that git source.

For Mac builds against the local Crepuscularity checkout, pin both crates to
the already-fetched checkout matching crepuscularity’s `Cargo.lock` rev
`c738623ffbcec2aeddc44a645cc6b74646d5cf97`, e.g.:

```toml
gpui = { path = "~/.cargo/git/checkouts/gpui-ce-…/c738623/crates/gpui", default-features = false, features = ["font-kit"] }
gpui_platform = { path = "~/.cargo/git/checkouts/gpui-ce-…/c738623/crates/gpui_platform", features = ["font-kit"] }
```

and mirror the same path pins in the local
`crepuscularity/{Cargo.toml,crates/crepuscularity-gpui,crepuscularity-runtime}/Cargo.toml`
(workspace + those crates). Keep those pins **out of** the crepuscularity git
index — they are machine-local until gpui-ce tip is fixed.

Enable `font-kit` on **both** `gpui` and `gpui_platform` or the window renders
with no text.
