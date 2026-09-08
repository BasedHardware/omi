# Omi Simulator (v5) — Crepuscularity / GPUI

Full **Rust** desktop simulator for local React Native v5 BLE discovery.

## What Crepuscularity is here

**Crepuscularity** ([https://crepuscularity.tsc.hk](https://crepuscularity.tsc.hk), repo [`tschk/crepuscularity`](https://github.com/tschk/crepuscularity)) is the **multi-target UI framework** (GPUI / web / native / SwiftUI View IR / etc).

In this tool it is wired as the **GPUI desktop UI shell** only — **not** an Omi API base URL, branding CDN, or firmware host.

BLE remains a **local CoreBluetooth GATT peripheral** (via [`ble-peripheral-rust`](https://crates.io/crates/ble-peripheral-rust) on Apple). There is **no HTTP backend**.

## Layout

```
tools/OmiSimulator/          ← Rust Crepuscularity GPUI app (this tree)
  Cargo.toml                 ← git pins → tschk/crepuscularity + gpui-ce
  .cargo/config.toml.example ← optional local path override (do not commit config.toml)
  src/main.rs                ← Crepus view! UI
  src/ble.rs                 ← Omi Devkit peripheral (DIS/battery/features/button/settings/audio)
  src/audio.rs               ← cpal mic → 8 kHz PCM16 notify frames (best-effort)
```

Dependencies are **git pins** in `Cargo.toml` (no absolute machine paths):

- `crepuscularity-gpui` → `https://github.com/tschk/crepuscularity` @ `afaabfc9…` (`pin/gpui-ce-c738623`, which pins transitive `gpui-ce` to `c738623…`)

Optional machine-local path overrides: copy `tools/OmiSimulator/.cargo/config.toml.example` → `config.toml` (gitignored). Do **not** commit `config.toml`.


Enable `font-kit` on **both** `gpui` and `gpui_platform` or the window renders
with no text.
