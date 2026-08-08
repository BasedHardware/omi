# Prototype: macOS WKWebView shell hosting a TS surface

Overnight spike, 2026-08-06. Tests the desktop analog of ADR-002 ("web UI in a native shell over a typed generated bridge") on macOS — the outlier platform, where the existing app is a ~274k-LOC SwiftPM executable and small Swift changes are structurally expensive.

Status: **prototype, not a proposal.** Nothing is signed, notarized, sandboxed for release, or production-shaped. One machine, one session (Apple silicon, macOS 26.6, Swift 6.2.3, Node 24.12), warm toolchain caches unless stated.

### Timings

| # | Measurement | Result | Notes |
|---|---|---|---|
| a1 | Cold: shell build from clean output dir | **1.7 s** | `swiftc -O`, 363 Swift LOC incl. generated |
| a2 | Cold: shell build, first ever (cold module cache) | **22.9 s** | one-time AppKit/WebKit module priming |
| a3 | Cold: surface (codegen + static build) | **0.07 s** | 0.02 s codegen + 0.05 s type-strip |
| a4 | Cold: dev server up and serving | **0.08 s** | no bundler, no watcher warm-up |
| b1 | **Warm UI loop:** edit `.ts` → reload pushed to client | **38–39 ms** | fs.watch → 25 ms debounce → SSE |
| b2 | **Warm UI loop:** edit `.ts` → all assets re-served | **62–84 ms** (n=3) | full-reload semantics; paint within a frame |
| c1 | **Warm native loop:** edit Swift handler → live in relaunched shell | **~5.0 s** (5.07/5.03/7.15) | kill + regen + swiftc + relaunch + reload |
| c2 | Warm native loop, first run of a fresh binary | **13.1 s** | one-off Gatekeeper assessment, unsigned binary |
| c3 | Shell launch → surface fetched | **184–240 ms** (n=3) | cold process each time |
| d1 | **Baseline:** clean `swift build -c debug` of the real macOS app | **227.2 s (3 m 47 s)** | 289 tasks, redirected `--scratch-path`, 6.3 GB products |
| d2 | **Baseline:** no-op `swift build` of the real app (zero edits) | **19.1 s** | relink alone; the *floor* of that app's native inner loop |

Reading of d1: **I could not reproduce a 10–30 minute build.** Debug SwiftPM build of `desktop/macos/Desktop` is under 4 minutes here with the SPM dep cache populated. The 10–30 min figure likely reflects release config, CI lanes, signing/notarization, or dep fetches — worth pinning down before it's quoted as the baseline. **d2 is the number that matters for G1:** even a no-op touch costs ~19 s there vs ~0.07 s for a UI edit here (~270× on the inner loop), and ~5 s when the edit is genuinely native.

### Does the typed-bridge-from-contract pattern scale?

Yes, with caveats.

Worked well: one 67-line contract produced 242 LOC across two languages; adding a message is a 4-line edit regenerating in 20 ms. Drift is a **compile error** — the generated Swift `BridgeHandling` protocol won't conform until every request is implemented, and `generate.mjs --check` is a 20 ms CI gate on stale generated files (same discipline as the OpenAPI compat gate, ~1/1000th the cost). The generator is 203 LOC of plain Node — no Pigeon-class tooling, no build plugin.

Needs real work:
- **No TypeScript typechecker ran.** `stripTypeScriptTypes` erases types without checking them; no `tsc` installed. The TS half of G4 is currently unenforced.
- **Nullability is asymmetric.** Swift's `JSONEncoder` omits `nil`, so generated TS declares `field?: T | null` to accept both — the contract's `optional` flag is enforced loosely on the wire.
- **Only request/response + fire-and-forget events are modelled.** No streaming, cancellation, backpressure, timeouts, or contract versioning against older surfaces. `/listen`-shaped capabilities need all of those, and that's where a hand-rolled generator stops being cheap.
- Errors are stringly-typed. `NativeHandlers` is `@unchecked Sendable`; under the real app's `-strict-concurrency=complete`, handler isolation is a design decision.

### Risks probed

**Native feel — mostly fine, two real gaps.** The webview answers `copy:`/`paste:`/`selectAll:` as first responder, so a standard AppKit Edit menu drives the surface with no bridge code; **`undo:` does not reach it.** Cmd-R reload, full-screen, Tab focus rings work; the page follows system appearance automatically (`effectiveAppearance=DarkAqua`). Gaps: (1) WKWebView does **not** support `-webkit-app-region: drag` — the Electron draggable-titlebar trick doesn't exist, so HTML window chrome costs native drag regions; (2) `allowsMagnification` is off by default.

**Frame pacing: not measured.** Every headless attempt returned `document.visibilityState === "hidden"`, suspending `rAF` and timers. The native probe explains it: `windowOccluded=true, appActive=false` — the window sat behind a full-screen terminal, so WebKit parked the page. This is itself a finding: **a surface driving UI from `rAF`/`setInterval` stalls when its window is occluded, while native-pushed `evaluateJavaScript` still executes.** Any background-updating surface (menu-bar popover, always-on capture status) must not depend on page timers. Scroll/typing feel needs a human; unverified.

**ATS / local loopback: no friction.** `http://127.0.0.1:<port>` loads with **no** `NSAppTransportSecurity` keys in `Info.plist` at all. Control: plain `http://` to a non-loopback host is blocked (lands on `about:blank`). The dev loop needs no security opt-outs and doesn't weaken the shipped app's ATS posture.

**Production loading is unsolved.** `loadFileURL` + `allowingReadAccessTo` loads the HTML but the ES module never executes (0 rendered cards, no bridge global) — `file://` module imports are blocked. Shipping a bundled surface needs a `WKURLSchemeHandler` custom scheme. Not built; ~half a day, and it changes nothing about the dev loop.

**Sandbox / hardened runtime: clean, one dependency.** Ad-hoc-signed probes: hardened runtime alone → bridge works (the JIT-bearing WebContent process is Apple-signed and separate, so `allow-jit` isn't needed); App Sandbox + `com.apple.security.network.client` → works; App Sandbox **without** `network.client` → dead, i.e. loopback HTTP counts as client networking. The shipping app runs `app-sandbox = false`, so not a blocker; a bundled-scheme path sidesteps it. No signing/notarization needed to build or run; only cost was a one-time ~8 s Gatekeeper assessment per freshly written unsigned binary (c2).

**Memory: +56 MB for the webview, across 3 extra processes.** Physical footprint, same window and content:

| | Processes | Physical footprint |
|---|---|---|
| Webview shell | app 20 MB + WebContent 32 MB + GPU 14 MB + Networking 8 MB | **74 MB** |
| Native AppKit window (control) | app only | **18 MB** |

GPU/Networking are per-app, so a second surface in the same process pool should add roughly a WebContent (~32 MB), not another 56 MB — untested. Affordable for desktop, but it's 4 processes in crash/telemetry data instead of 1.

### Verdict on ADR-002's desktop analog

**The bet holds on macOS, and the desktop case is stronger than the mobile one.** The two things that could have killed it did not: loopback content triggers no ATS/security friction, and the typed generated bridge is genuinely cheap with drift caught at compile time. The inner-loop payoff is the headline: **0.07 s for a UI edit against a ~19 s floor** — a change in kind, not a margin. When a change *is* native, this shell rebuilds in 1.7 s because it's 363 lines, not 274k: the shell staying thin is what preserves the loop, which is exactly the doctrine already recorded for the macOS agent ("Swift is a transport and presentation client").

Three tempering facts: (1) native feel is only partly verified — menu/appearance/keyboard basics pass mechanically, scroll and typing need a human, and the titlebar-drag gap means custom chrome costs native code; (2) the production load path (custom scheme handler) is unbuilt, so nothing here proves the shipping configuration; (3) the bridge is request/response only, and the capability most likely to migrate early (anything `/listen`-shaped) needs streaming semantics the generator doesn't model.

Recommended next step if pursued: pick one real, narrow, non-streaming macOS surface, ship it behind the custom-scheme loader, and make native-quality acceptance a human checklist on that screen — not another prototype.

### Open questions for David

1. **What is the real macOS build baseline?** I measured 3 m 47 s clean debug and 19 s no-op, not 10–30 min. If 10–30 min comes from release/CI/notarization lanes, the G1 target should be stated against the loop developers actually pay (~19 s floor).
2. **Is a `tsc --noEmit` gate acceptable as a dependency?** Without it the TS half of G4 is unenforced. Strictness and zero-deps are in tension.
3. **Bundled vs downloaded surface on desktop.** ADR-002 leans on webviews as the sanctioned OTA path on iOS. Does desktop want the same OTA property (implying a custom scheme handler *and* an update/integrity story), or is bundling-per-release enough for macOS?
4. **Does the bridge contract get its own schema pipeline, or ride an existing one?** Today it's a bespoke `bridge.json`. With three OpenAPI surfaces plus Pigeon already, is a shared IDL worth it before the second surface ships?
5. **Streaming in the bridge contract:** model streams/cancellation in v1, or defer given the first migrations are request/response?
6. **Who owns the 4-process footprint in telemetry?** Crash/memory reporting assumes one process; does observability need to know about WebContent before a surface ships?

### Reproducing

```sh
node codegen/generate.mjs            # regenerate both sides
node codegen/generate.mjs --check    # drift gate (exit 1 if stale)
node surface/devserver.mjs           # dev server + live reload on 127.0.0.1:5290
OMI_BUILD_DIR=<scratch> scripts/build-shell.sh    # unsigned .app, no Xcode project
OMI_BUILD_DIR=<scratch> scripts/run-shell.sh      # native inner loop: kill, rebuild, relaunch
```

Built-in diagnostics: `OMI_SURFACE_PATH=/?selftest=1` (headless bridge round-trip), `?perf=1` (frame pacing; needs a non-occluded window), `OMI_PROBE_NATIVE=1` (responder/appearance/occlusion), `OMI_PROBE_JS=<expr>` + `OMI_PROBE_EXIT=1`, `OMI_SURFACE_DIR=<dir>` / `OMI_SURFACE_URL=<url>` (alternative load strategies).
