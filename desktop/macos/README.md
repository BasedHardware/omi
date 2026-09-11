# OMI Desktop

macOS app for OMI — always-on AI companion. Swift/SwiftUI frontend, Python backend.

## Structure

```
Desktop/          Swift/SwiftUI macOS app (SPM package)
../../backend/    Python API server (Firestore, Redis, auth, LLM)
agent/            Agent runtime for multi-provider chat (TypeScript)
dmg-assets/       DMG installer resources
```

## AI Providers

Chat runs through one of three providers, chosen in Settings > AI Provider:

- **Omi AI** — the default, routed through the Rust backend with your Omi account.
- **Claude Code** — your own Claude OAuth session.
- **Local** — talks directly to a self-hosted OpenAI-compatible server (e.g. LM Studio, Ollama). Set the server's base URL and pick a model from the list it fetches at `{baseURL}/models`; no chat prompt or completion is ever routed through Omi's servers or Anthropic. An optional second "vision" model can be configured to interpret screenshots. The agent process still authenticates its own tool calls into Omi storage (memories, conversations) with your Firebase session, which is a data fetch, not a model call. Running Local with no self-hosted backend URL at all is a fully supported configuration: chat, push-to-talk, and screen capture are never paywalled or metered against the free plan while Local is active, since those calls never touch Omi's cloud model. Only voice transcription needs a self-hosted backend to leave Omi's Deepgram proxy.

  A single Settings field, **Cloud-assisted features** (off by default), gates everything under Local that would otherwise still call a cloud model: connector synthesis (Apple Notes, Calendar, Gmail, AI-profile), proactive assistants and live notes (task/memory/suggestion/insight extraction from screen and transcripts), dictation polish, Rewind semantic-search embeddings, and web search. All of these fail closed under Local until you opt in (a clear log line or tool-result message, never a silent no-op or a retry loop) and are metered exactly like a cloud user once you do. An existing pre-unification "Connector synthesis" choice migrates forward automatically the first time it's read.

  Named dev bundles (`OMI_APP_NAME=omi-*`) keep their Local provider selection across `./run.sh` relaunches: the settings seed (`scripts/omi-settings-seed.sh`) never mirrors the AI Provider choice over a bundle already set to Local, because Local's endpoint keys (`localLLMBaseURL` and friends) are bundle-local and would otherwise be left pointing nowhere.

  A **Context per turn** picker (25%, 50%, 75%, 100% default) trims how much of the kernel context snapshot the runtime sends on the first turn of a chat, keeping fewer recent journal turns and trimming the largest context sources on the local model; changing it restarts the local bridge.

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
