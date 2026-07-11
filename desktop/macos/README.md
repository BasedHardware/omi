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
```

`--yolo` targets the deployed development services. Those services currently use production Firebase identities and data stores, so use a named `omi-*` bundle for isolated desktop state and avoid treating it as an offline data sandbox.

`run.sh` auto-detects an `Apple Development` or `Developer ID Application` signing identity from your login keychain. Override with `OMI_SIGN_IDENTITY="..." ./run.sh`.

Named bundles derive an isolated bundle ID and OAuth callback URL scheme from `OMI_APP_NAME`. `Omi Dev` keeps `com.omi.desktop-dev` / `omi-computer-dev`, while `OMI_APP_NAME="omi-subagent-test"` uses `com.omi.omi-subagent-test` / `omi-omi-subagent-test`. The app reads that scheme from `CFBundleURLTypes` for OAuth redirects, so parallel dev bundles do not claim the canonical `omi-computer-dev` callback.

## License

MIT
