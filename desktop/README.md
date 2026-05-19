# OMI Desktop

macOS app for OMI — always-on AI companion. Swift/SwiftUI frontend, Rust backend.

## Structure

```
Desktop/          Swift/SwiftUI macOS app (SPM package)
Backend-Rust/     Rust API server (Firestore, Redis, auth, LLM)
local-backend/    Local-first daemon for desktop MVP testing
agent/            Agent runtime for multi-provider chat (TypeScript)
agent-cloud/      Cloud agent service
dmg-assets/       DMG installer resources
```

## Development

Requires macOS 14.0+, Rust toolchain, code signing with an Apple Developer ID, and
Homebrew `webp` for the Swift app (`brew install webp`).

```bash
# Run (builds Swift app, starts Rust backend, launches app)
./run.sh

# Run with the prod backend (skips local Rust + tunnel)
./run.sh --yolo

# Run in local daemon mode and let the dev launcher start/check the daemon
OMI_DESKTOP_BACKEND_MODE=local OMI_LOCAL_DAEMON_SUPERVISE=1 ./run.sh
```

`run.sh` auto-detects an `Apple Development` or `Developer ID Application` signing identity from your login keychain. Override with `OMI_SIGN_IDENTITY="..." ./run.sh`.

Local daemon mode uses `http://127.0.0.1:8765` by default. To manage the daemon yourself, run `cd desktop/local-backend && cargo run`, verify `curl http://127.0.0.1:8765/health`, then launch desktop with `OMI_DESKTOP_BACKEND_MODE=local ./run.sh`. The launcher only targets the dev app bundle (`Omi Dev.app` / `com.omi.desktop-dev`) and does not modify the production app.

## License

MIT
