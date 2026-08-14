# Prototype: Flutter shell hosting a TS surface in a webview

Overnight spike validating ADR-002's actual bet: Flutter stays the mobile shell, new product surfaces arrive as webview-hosted TS over a typed shell↔surface bridge. Question asked: **does the bridge work, and is the iteration loop good enough to build in?**

Answer: **yes on both, with three concrete constraints that change the design** (Findings 1–3). Everything below was measured on an iOS simulator, not reasoned about.

## What was built and what ran

| Piece | Path | Status |
| --- | --- | --- |
| Bridge contract (single source of truth) | `contract/bridge.contract.json` | 3 messages, 4 types |
| Codegen (contract → Dart + TS) | `tools/gen-bridge.mjs` | runs, ~240 generated lines |
| Flutter shell | `app/` | runs on iOS simulator, `flutter analyze` clean |
| TS surface | `surface/` | runs in both ship and dev mode |
| Dev server + live reload | `tools/serve.mjs` | runs, sub-2s reload |

Bridge messages exercised end to end, both directions: `getDeviceState` (ui→shell request), `startListening` (ui→shell command), `transcriptEvent` (shell→ui push, streamed as growing partials then a final).

Environment: Flutter 3.44.6 from the team's `fvm` cache (the app pins no `.fvmrc`), `webview_flutter 4.13.0` — the exact version `omi:app` already pins, so no new dependency. iOS 26.2 simulator (iPhone 17), Xcode 26.2. Test target (a) macOS desktop was **skipped deliberately**: `webview_flutter` has no macOS implementation, and using a different plugin for desktop would have tested a bridge the real app can't ship. Target (b), the iOS simulator, worked on the first attempt.

The shell can drive the surface unattended (`--dart-define=AUTODRIVE=true`) and pipes `console.log` into the Flutter log, so all numbers below came out of a headless run.

## Measurements

| Loop | Time | Notes |
| --- | --- | --- |
| Edit surface TS → visible change, **dev mode** | **1.8 s** | bundle 0.10 s + watch/poll + reload |
| Edit surface TS → visible change, **ship (asset) mode** | **~15 s** | rebuild+reinstall; hot reload does *not* work (Finding 1) |
| Edit Dart bridge/shell → hot restart | **0.24–0.29 s** reported, 0.66 s wall | surface reloads with it |
| Cold `flutter run` (fresh project, pods + Xcode build) | **~100 s** (Xcode build 61 s) | one-time |
| Warm `flutter run` → surface interactive | **15.2 s** (Xcode build 6–12 s) | |
| Contract change → regenerated Dart + TS | **<0.2 s** | |

Bridge latency, 100 sequential ui→shell→ui round trips (`getDeviceState`), 10 warm-up calls, debug build, simulator:
- **mean 0.39–0.44 ms/call** (39–44 ms wall for 100 round trips), consistent across three runs
- p50 0 ms, p95 1–2 ms, max 2–3 ms
- shell→ui push one-way (`transcriptEvent`, shell-stamped): **0–3 ms**, typically 1–2 ms

Caveat that matters: WKWebView clamps `performance.now()` to ~1 ms, so percentiles are coarse by construction — the wall-clock total over N calls is the trustworthy figure. The bridge is not the bottleneck: a JSON round trip costs well under one frame, and debug-mode Dart is the slow case.

## Findings

**1. Asset (ship) mode has no fast loop, and it is not a caching problem.** Flutter's hot reload syncs changed assets into an override directory on the device, but `loadFlutterAsset` resolves against the *app bundle*, which hot reload does not rewrite. Verified directly: after an asset rebuild + hot reload, the override copy on the simulator contained the new code while the bundle copy did not, and the webview kept running the old surface. So **dev mode (http) is the only fast loop; asset mode requires a rebuild.** The dev-server path is therefore not a convenience — it is the development mode, and must be first-class and non-optional.

**2. ES modules do not load from `file://`.** The first ship-mode run rendered HTML and CSS perfectly and executed *nothing*: `<script type="module">` is silently blocked by CORS on WKWebView's opaque `file://` origin. Fix was an IIFE bundle plus a classic `<script defer>`. Consequence: **no native ESM, no dynamic `import()`, no import maps in asset mode** — a real constraint on how the shared TS core is packaged for mobile, and one a browser- or dev-server-only test would never have caught.

**3. A `file://` surface cannot reach the network at all.** Probed explicitly: `NETPROBE blocked origin=file: err=Load failed`. In shipped asset mode the surface cannot call `api.omi.me` or anything else directly — **all network access must go through the bridge, or the surface must be served from a real origin** (loopback server or custom URL scheme). This is an architectural fork, not a detail: either the bridge grows into a data-fetch channel (shell owns auth/transport, consistent with the existing thin-shell doctrine and the "native owns lifecycle" rulings), or the shell hosts surfaces over a proper origin.

**4. The generated-bridge discipline paid for itself immediately.** The Dart side is an `abstract` handler, so the compiler names every unimplemented message; TS gets typed calls and typed push subscriptions. Contract changes regenerated both sides in under a second and the type errors pointed at exactly the work. This is the Pigeon pattern (`omi:app/lib/gen/pigeon_communicator.g.dart`) applied one layer out, and it behaves the same. ~90 lines of contract + generator produced both sides.

**5. Rendering quality is high; tactile feel is untested.** Screenshots in both modes are indistinguishable from a native dark-mode screen: correct system font, correct safe-area insets, crisp text, no webview chrome, no white flash (webview background set to match). Honest limits: a headless simulator run cannot judge scroll momentum, rubber-banding, or keyboard behaviour, and `input.focus()` cannot raise the keyboard without a user gesture, so the keyboard path was **not** exercised. Those probes are built into the surface and ready for a five-minute hands-on device pass — which is where ADR-002's "webview quality is an explicit acceptance gate" check actually has to happen.

## OTA path (App Store 3.3.2)

The prototype's two modes are the two halves of the OTA story: the surface is loaded from a path the shell picks at runtime, and the bridge does not care where the surface came from. Extending ship mode to OTA needs:

1. A versioned bundle downloaded to app storage, loaded via `loadFile` / `loadFileWithParams` instead of `loadFlutterAsset` (both exist in `webview_flutter_wkwebview`; the read-access directory parameter is what lets a downloaded bundle load its sibling files).
2. A bundled baseline surface as fallback, plus contract-version gating — a downloaded surface declares the bridge contract version it needs and the shell refuses bundles it cannot serve. The contract carries a version and both generated sides expose it; enforcement is unwritten.
3. A rollback path: keep the previous bundle, revert if the new one fails to signal readiness over the bridge.

Guideline fit looks sound — downloaded code is JavaScript executed in WKWebView, the sanctioned category, and it does not change the app's purpose. Two cautions. Finding 3 applies to downloaded bundles too: a `file://`-hosted OTA surface is network-isolated. And `webview_flutter` does not expose `WKURLSchemeHandler`, so "serve the bundle from a custom scheme" is unavailable without a plugin change or moving to `flutter_inappwebview` — a dependency decision to make once, up front. Also: the app already carries `shorebird.yaml`; how a JS-bundle OTA channel coexists with Shorebird's Dart code push is an open policy question, not a technical one.

## Verdict

The ADR-002 bet is **technically sound and pleasant to work in**. The bridge is fast enough to ignore (sub-millisecond), the codegen discipline transfers cleanly from Pigeon, and the dev-mode loop (1.8 s surface edits, 0.3 s Dart restarts) is better than the Flutter-native loop it replaces. ~600 authored lines reached working end-to-end state in one session with no new dependency.

The real constraints are not about speed, they are about the `file://` origin: no ESM, no network, no fast reload. All three push the same direction — **serve surfaces from a real origin rather than raw bundled assets**, and treat the bridge as the shell's authoritative channel for anything privileged.

## Open questions

1. Does the surface fetch data itself (needs a real origin) or does the bridge carry it (shell owns auth/transport)? Finding 3 forces this choice; it deserves an ADR.
2. If a real origin is needed: loopback HTTP server in the shell, or custom URL scheme (which means leaving `webview_flutter` for `flutter_inappwebview`)?
3. Hands-on device pass on scroll/keyboard/back-gesture feel — the one thing this spike could not measure and the thing ADR-002 makes an acceptance gate.
4. How does JS-bundle OTA coexist with the existing Shorebird Dart code-push channel?
5. Pigeon-driven contract (reuse existing generator) or standalone schema as here (needed anyway to emit TS)?
6. Multiple concurrent surfaces/microapps: one webview per surface, or one webview with routing? Untested — this prototype hosts a single full-screen surface.

## Addendum 2026-08-06: ship-origin spike (open questions 1–2 answered)

The loopback half of the origin fork was run empirically here: `--dart-define=SURFACE_MODE=loop` starts an in-app Dart `HttpServer` (`app/lib/loop_server.dart`) serving a real multi-file ESM probe surface (`surface/loop/`, built by `tools/build-loop.mjs`) from 127.0.0.1. Findings, evidence, the candidate comparison, and the recommendation (custom-scheme/asset interception, not loopback, for mobile ship mode) are in [docs/reviews/ship-origin-spike.md](../../docs/reviews/ship-origin-spike.md). Headline measurements: ESM + dynamic import work over loopback; storage is keyed on the port (ephemeral port = silent wipe, fixed port persists across relaunch); external https CORS fetch works; ATS still blocks external cleartext with zero plist keys; Secure cookies are dropped; chunked streaming +3–6 ms and WebSocket +6–22 ms work; client `AbortController` cancel never surfaced server-side (flush hang caught by watchdog only).

## Addendum 2026-08-06 (later): plugin spike — custom-scheme half run empirically

Candidate B was then also run end-to-end here: a ~170-line `WKURLSchemeHandler` in `app/ios/Runner/AppDelegate.swift` (spike-only swizzle injection, since `webview_flutter` exposes no configuration hook) serves versioned bundle dirs at `omi-ui://local/`, driven by `app/lib/scheme_host.dart` + `surface/scheme/` + `tools/build-scheme.mjs` (`--dart-define=SURFACE_MODE=scheme`, self-driving 5-phase machine, evidence in the app container's `Documents/probe-log.txt`). Results — ESM works, storage persists across restarts and bundle swaps (`bootCount` 1→12 over 3 processes), `Origin: omi-ui://local` captured, bridge unchanged at 0.36–0.48 ms/call, contract gate blocks a mismatched bundle before navigation, handler survives suspension — are in the "Plugin spike results" addendum of [docs/reviews/ship-origin-spike.md](../../docs/reviews/ship-origin-spike.md).

## Running it

```bash
node tools/gen-bridge.mjs                 # contract -> Dart + TS
node tools/build-surface.mjs --ship       # bundle surface into app assets
cd app && flutter run -d <ios-sim-udid>   # ship mode

# dev mode (fast loop): in one shell
node tools/serve.mjs
# in another
cd app && flutter run -d <ios-sim-udid> --dart-define=SURFACE_MODE=dev
# add --dart-define=AUTODRIVE=true to drive the surface and print bench numbers headlessly
# a real device also needs --dart-define=SURFACE_HOST=<mac-lan-ip>:8787
```
