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

# Run with the prod backend (skips local Rust + tunnel)
./run.sh --yolo
```

`run.sh` auto-detects an `Apple Development` or `Developer ID Application` signing identity from your login keychain. Override with `OMI_SIGN_IDENTITY="..." ./run.sh`.

## License

MIT
