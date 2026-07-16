# OMI Desktop

macOS app for OMI — always-on AI companion. Swift/SwiftUI frontend, Rust backend.

## Structure

```
Desktop/          Swift/SwiftUI macOS app (SPM package)
Backend-Rust/     Rust API server (Firestore, Redis, auth, LLM)
agent/            Agent runtime for multi-provider chat (TypeScript)
agent-cloud/      Cloud agent service
dmg-assets/       DMG installer resources
```

## Development

Requires macOS 14.0+, Rust toolchain, and code signing with an Apple Developer ID.

```bash
# Run (builds Swift app, starts Rust backend, launches app)
./run.sh

# Run an isolated named bundle for parallel testing
OMI_APP_NAME="omi-subagent-test" ./run.sh

# Run with the dev backend (skips local Rust + tunnel)
./run.sh --yolo

# Keep one explicit focused regression test running after each save
./scripts/dev-feedback.py --watch swift 'ChatTests/testSendsMessage'
./scripts/dev-feedback.py --watch rust 'handles_timeout'

# Relaunch an already-built named app without holding the terminal open.
# Supply a harness/external backend; --no-wait deliberately does not own one.
OMI_SKIP_BACKEND=1 OMI_APP_NAME="omi-subagent-test" ./run.sh --yolo --fast-only --no-wait

# Force a complete bundle refresh after changing packaged runtime inputs
./run.sh --full
```

`--yolo` targets the deployed development services. Those services currently use production Firebase identities and data stores, so use a named `omi-*` bundle for isolated desktop state and avoid treating it as an offline data sandbox.

`run.sh` auto-detects an `Apple Development` or `Developer ID Application` signing identity from your login keychain. Override with `OMI_SIGN_IDENTITY="..." ./run.sh`.

After a successful full launch, `run.sh` automatically uses its fast lane for ordinary Swift-only edits: it incrementally builds Swift, patches the already-installed app executable plus the current desktop API URL, re-signs it, and relaunches. Named local-harness profiles are eligible too; their current disposable `.env` is refreshed on every fast patch rather than cached. Changing package metadata, bundled resources, agent/runtime inputs, entitlements, or persistent launch configuration safely falls back to the complete packaging path. Use `./run.sh --full` (or `OMI_FORCE_FULL_BUNDLE=1`) to force that path; set `OMI_SCAN_STALE_BUNDLES=1` only when recovering from stale LaunchServices registrations.

`dev-feedback.py` is the fast test loop: pass an explicit XCTest or Cargo filter, use `--once` for one check or `--watch` to rerun after relevant saves. It never guesses coverage and never replaces `./test.sh`, which remains the full component/PR suite. That suite now runs its isolated Swift suites with four workers by default; use `OMI_SWIFT_TEST_SUITE_WORKERS=1` only when diagnosing concurrency-sensitive behavior. For a direct local Rust backend, `run.sh` now uses Cargo debug builds and reuses a healthy worktree-owned backend on Swift-only relaunches. Set `OMI_DESKTOP_BACKEND_RELEASE=1` only when locally checking optimized backend behavior. Add `--no-wait` only when a harness or other external backend owns the API; it returns after the app launch instead of holding the terminal for launcher-managed processes.

`git push` is the desktop acceptance gate: for desktop CI-selected changes it runs the same four-worker Swift suite as GitHub Actions through `scripts/run-swift-ci.sh`, plus a clean release compile when `Package.swift` or `Package.resolved` changes. It requires the pinned `/Applications/Xcode_16.4.app` (Xcode 16.4 build 16F6) and fails instead of silently using another toolchain. Keep ordinary iteration on your installed Xcode with `dev-feedback.py --watch`; install the pinned Xcode before relying on push readiness.

Named bundles derive an isolated bundle ID and OAuth callback URL scheme from `OMI_APP_NAME`. `Omi Dev` keeps `com.omi.desktop-dev` / `omi-computer-dev`, while `OMI_APP_NAME="omi-subagent-test"` uses `com.omi.omi-subagent-test` / `omi-omi-subagent-test`. The app reads that scheme from `CFBundleURLTypes` for OAuth redirects, so parallel dev bundles do not claim the canonical `omi-computer-dev` callback.

## License

MIT
