# OMI Desktop

macOS app for OMI — always-on AI companion. Swift/SwiftUI frontend, Python backend.

## Structure

```
Desktop/          Swift/SwiftUI macOS app (SPM package)
../../backend/    Python API server (Firestore, Redis, auth, LLM)
agent/            Agent runtime for multi-provider chat (TypeScript)
dmg-assets/       DMG installer resources
```

## Development

Requires macOS 14.0+, Python 3.11 with uv, and code signing with an Apple Developer ID.

```bash
# Run (builds Swift app, starts Python backend, launches app)
./run.sh

# Run an isolated named bundle for parallel testing
OMI_APP_NAME="omi-subagent-test" ./run.sh

# Run with the dev backend (skips local Python + tunnel)
./run.sh --yolo

# Keep one explicit focused regression test running after each save
./scripts/dev-feedback.py --watch swift 'ChatTests/testSendsMessage'
./scripts/dev-feedback.py --watch python 'tests/unit/test_desktop_chat.py'

# Relaunch an already-built named app without holding the terminal open.
# Supply a harness/external backend; --no-wait deliberately does not own one.
OMI_SKIP_BACKEND=1 OMI_APP_NAME="omi-subagent-test" ./run.sh --yolo --fast-only --no-wait

# Force a complete bundle refresh after changing packaged runtime inputs
./run.sh --full
```

`--yolo` targets the deployed development services. Those services currently use production Firebase identities and data stores, so use a named `omi-*` bundle for isolated desktop state and avoid treating it as an offline data sandbox.

`run.sh` auto-detects an `Apple Development` or `Developer ID Application` signing identity from your login keychain, then falls back to a self-signed `Omi Local Dev Signing` identity if you have one. Override with `OMI_SIGN_IDENTITY="..." ./run.sh`. See [`docs/local-code-signing.md`](docs/local-code-signing.md) for how to create that identity and why a signing identity's Team ID decides the local entitlements.

Agent runtime preparation keeps the universal Node binary in a shared cache at `~/Library/Caches/OmiDesktop/node-runtime` when that directory is on the same APFS volume as the worktree, and otherwise at `<volume>/.omi-cache/OmiDesktop/node-runtime` on the worktree's own volume. Staging clones the binary only in that case. `OMI_AGENT_RUNTIME_NODE_CACHE_DIR` overrides the location. CI builds that binary in the worktree and does not use the shared cache. Set `OMI_AGENT_RUNTIME_FORCE_REBUILD=1` to rebuild and refresh the cache.

After a successful full launch, `run.sh` automatically uses its fast lane for ordinary Swift-only edits: it incrementally builds Swift, patches the already-installed app executable plus the current desktop API URL, re-signs it, and relaunches. Named local-harness profiles are eligible too; their current disposable `.env` is refreshed on every fast patch rather than cached. Changing package metadata, bundled resources, agent/runtime inputs, entitlements, or persistent launch configuration safely falls back to the complete packaging path. Use `./run.sh --full` (or `OMI_FORCE_FULL_BUNDLE=1`) to force that path; set `OMI_SCAN_STALE_BUNDLES=1` only when recovering from stale LaunchServices registrations.

`dev-feedback.py` is the fast test loop: pass an explicit XCTest filter or pytest path, use `--once` for one check or `--watch` to rerun after relevant saves. A filter matching zero tests is reported as a failure, not a pass. It never guesses coverage and never replaces `./test.sh`, which remains the full component/PR suite. That suite runs isolated Swift suites with four workers locally. CI uses two workers: each has a copy-on-write SwiftPM scratch directory plus an isolated Foundation runtime home, so filtered `--skip-build` processes do not share build locks, preferences, Application Support, caches, or temporary files. Use `OMI_SWIFT_TEST_SUITE_WORKERS=1` when diagnosing concurrency-sensitive behavior. `run.sh` reuses a healthy worktree-owned Python backend on Swift-only relaunches. Add `--no-wait` only when a harness or other external backend owns the API; it returns after the app launch instead of holding the terminal for launcher-managed processes.

`git push` is the bounded desktop acceptance gate: desktop source changes run only the fast `xcrun swift build -c debug --package-path Desktop` check on the installed Xcode. This is intentionally less than CI: the parallel, isolated Swift suite, clean release compile, and the pinned Xcode (version + build + expected app path live in `ci/xcode-pin.json`, the single source shared with GitHub Actions and Codemagic) belong to CI. Do not move those CI jobs into pre-push; preserving push-time budget keeps normal iteration fast. Use `dev-feedback.py --watch` while editing.

Generated-client-only PRs (every changed `desktop/macos/` path is under `Desktop/Sources/Generated/` and ends in `.generated.swift`) run static checks and `./scripts/run-swift-ci.sh --test-compile`: one debug build of the app and test target, without suites or launcher tests. Any other desktop path restores the normal selection. Linux Repo Checks verifies generated Swift against the committed app-client schema. PRs select the Xcode 27 advisory for Siri/App Intents, package/toolchain, metadata embedder, workflow, or selector inputs.

Main pushes retain debug tests and exact-SHA release compilation; scheduled/manual health runs retain their path-independent full coverage. Ordinary source/test PRs use debug verification, while release-specific PR inputs also select release compilation. On pinned Xcode 26.6, `./scripts/run-swift-ci.sh --release-test-compile` builds the app and every test target together with the ARM release triple and explicit testability. The notification boundary check then runs `./scripts/run-swift-ci.sh --release-notification-regression` with identical options and `--skip-build`; compile first. The hosted verify and release jobs each have a 90-minute ceiling.


Named bundles derive an isolated bundle ID and OAuth callback URL scheme from `OMI_APP_NAME`. `Omi Dev` keeps `com.omi.desktop-dev` / `omi-computer-dev`, while `OMI_APP_NAME="omi-subagent-test"` uses `com.omi.omi-subagent-test` / `omi-omi-subagent-test`. The app reads that scheme from `CFBundleURLTypes` for OAuth redirects, so parallel dev bundles do not claim the canonical `omi-computer-dev` callback.

## License

MIT
