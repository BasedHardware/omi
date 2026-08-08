# Focused runnable mobile shells

This directory is limited to React Native, Flutter, Lynx, and Valdi. Each candidate is evaluated against:

```text
omi-relay-contract:v1|native-seam:<framework boundary>|payload:bounded|gap:explicit
```

## Current evidence

| Shell | Command | Evidence |
|---|---|---|
| Flutter | `flutter analyze`; `MACOSX_DEPLOYMENT_TARGET=12.0 flutter build macos --debug` | Existing parity baseline; analyzer and macOS shell build |
| Lynx | `bun install && bun run build` | ReactLynx bundle builds; native module remains unverified |
| React Native | Existing project tests/builds | Android relay baseline; iOS compiler issue remains |
| Valdi | `valdi agent-check --module hello_world --json` | Resolver passes; full check currently fails build, lint, and tests |

Generated dependencies and external Valdi source remain ignored. Use Bun for JavaScript/TypeScript installation and scripts; do not use npm.

## Next gates

- React Native: real Android/iOS native-function adapter.
- Flutter: route the same contract through the existing Flutter host.
- Lynx: implement one native module and run the Android host.
- Valdi: complete a clean Android Bazel build, then run module tests.
