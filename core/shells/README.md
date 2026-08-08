# `core/shells/` — native hosting code

Per-platform hosting for the shared TypeScript surfaces: a loopback/scheme origin,
webview mounting, and the bridge bindings. Promoted here from the frontend tracker's
`prototypes/` under board ruling PR-6.

| Package | Path | Host |
| --- | --- | --- |
| `@omi-core/shell-macos` | `macos/` | AppKit + WKWebView, fixed-port loopback origin |
| `@omi-core/shell-ios` | `ios/` | Flutter + WKWebView, frozen `omi-ui://local` scheme origin |

## Launch it (the entry points)

**These two scripts are the stable, supported entry points.** A top-level dev-stack
launcher should call these and nothing deeper; the internals below them are free to move.

```bash
# macOS — LIVE against a local backend
core/shells/macos/scripts/dev-run-macos.sh --api http://127.0.0.1:4801

# iOS Simulator — LIVE against a local backend
core/shells/ios/scripts/dev-run-ios.sh --api http://127.0.0.1:4801
```

Both take the same flags and honour the same environment, so a launcher can treat them
uniformly:

| Flag / env | Meaning |
| --- | --- |
| `--api <url>` / `OMI_API_BASE_URL` | Backend base URL. Default `http://127.0.0.1:4801`. |
| `OMI_API_TOKEN` | Dev credential, held by the **shell**, never given to the page. |
| `OMI_DEV_TOKEN_ISSUER_URL` | Optional dev-mode issuer; used when no token is set. |
| `--fixture <name>` | **FIXTURE** mode — deterministic in-page data, bridge bypassed. |
| `--route <name>` | Live route to open (macOS). Default `home`. |
| `--accept` | Headless acceptance run; exits nonzero on **zero** served traffic. |
| `--device <udid>` | iOS only. Defaults to the booted simulator. |

Exit codes are meaningful. Both scripts **refuse to launch** rather than show you an
empty app when the backend is unreachable or no credential is available. That refusal is
deliberate: a shell that launches into an empty list is indistinguishable from a UI bug,
and that ambiguity is exactly how a dead data path once passed for a working one.

## LIVE vs FIXTURE — read this before believing a screenshot

`--fixture <name>` maps to a `qa=` surface route, which selects an in-page fixture store.
**It does not traverse the privileged HTTP bridge at all.** Nothing observed in fixture
mode is evidence about the backend, and a fixture screenshot can never support a
served-request count or an "it's talking to the backend" claim. Both scripts print a
banner saying so, in both modes, so the two can't be confused after the fact.

The honest tell at runtime is the **data itself**. Against the deterministic QA backend
the live route renders different content from the fixture route — different item counts
and rows that exist only server-side.

## The origin is frozen, and that is a storage invariant

macOS serves the surface from a fixed loopback port; iOS serves it from `omi-ui://local`.
Neither is a naming preference. `IndexedDB` and `localStorage` are **origin-keyed**, and
the port is part of the origin — so an ephemeral port or a per-version scheme is a silent
wipe of local surface storage on the next launch. `dev-run-macos.sh` warns loudly if you
override the port; the iOS origin is not configurable at all.

## Loopback binds are asserted, not assumed

`NWListener(using:on:)` binds **all interfaces** silently, and a previous `LoopbackServer`
published the app bundle to the LAN while every `127.0.0.1` check still passed.

```bash
core/shells/macos/scripts/verify-loopback.sh 4841
# VERDICT: loopback-bind PASS
```

It parses `lsof` for an exact `127.0.0.1` bind (so a `*:port` row cannot pass), then
requires a curl to this machine's LAN address to **fail**. A machine with no LAN address
reports `INCOMPLETE` and exits nonzero — a skipped check is never a pass. Verified by
negative control: a server bound to `0.0.0.0` is caught as
`VERDICT: loopback-bind FAIL (not-loopback)`.

## Verification

`pnpm verify` in `core/` runs the bridge gates against these packages: the Swift and Dart
mirrors of the security-bearing bridge constants, and a 20-row HTTP host-conformance table
generated for both hosts. Host enforcement policy exists twice (~180 lines of Swift and of
Dart) and a real bug was once exactly a porting divergence between them, so prefer growing
the generated conformance table over hand-porting a third copy.

Native verification is **screenshot + socket, not tests**. Name the evidence class:
`WKWebView.takeSnapshot` proves the surface rendered; desktop `screencapture` proves a
window composited; `simctl` proves both. A byte-identical "success" pair is a failed run.

## Toolchain

- macOS shell: `swiftc` only — no Xcode project, no SwiftPM, unsigned scratch bundle.
  Bundle names must match `omi-on-<scratch>`; a shipping `Omi` / `Omi Beta` bundle is
  never touched.
- iOS shell: **Flutter >= 3.44** (pubspec needs Dart `^3.12.2`). An older Flutter fails
  with a confusing "version solving failed"; `dev-run-ios.sh` warns explicitly.
