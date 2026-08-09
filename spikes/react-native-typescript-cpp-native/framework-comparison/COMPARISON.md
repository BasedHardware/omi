# Focused comparison: Valdi, Lynx, React Native, Flutter

## Decision question

Can these four candidates host TypeScript-first product logic while keeping native work behind a narrow, bounded contract?

Shared marker:

```text
omi-relay-contract:v1|native-seam:<framework boundary>|payload:bounded|gap:explicit
```

## Evidence matrix

| Candidate | Strength | Current proof | Blocking gap | Opinion |
|---|---|---|---|---|
| React Native | Best TypeScript ecosystem and native-module path | TypeScript MVP cockpit, full typed Omi capability contract tests, Bun lint/Jest/tsc, Android `assembleDebug`, C++ CTest | Real platform module and hardware execution still pending | Best TS-first baseline |
| Flutter | Strongest existing Omi/native parity | `flutter pub get`, `flutter analyze`, and macOS debug build pass | Dart owns the UI layer; no new native adapter in this spike | Safest shipping baseline |
| Lynx | Native-oriented TS/React model | Bun install, Rspeedy bundle, and Vitest pass | No real native-module Android/iOS run | Best challenger to RN |
| Valdi | Strong native-view and polyglot-module design | Bun dependency install and module resolution pass | Android Bazel build, lint, and tests fail | Highest-upside but currently highest-risk |

## What has been proven

- The four candidates can be represented against the same bounded relay contract.
- React Native has the strongest current TypeScript/mobile evidence.
- Flutter has the strongest existing Omi parity evidence.
- Lynx's TypeScript bundle path works locally with Bun/Rspeedy.
- Valdi's module resolver works, but its complete validation does not.

## What has not been proven

None of the four has yet demonstrated the complete target path on physical hardware:

```text
TypeScript product logic
        ↓
native function binding
        ↓
BLE/audio/background adapter
        ↓
real Android/iOS lifecycle
```

A host build or contract probe cannot establish that path.

## Valdi status

The official hello-world module currently reports:

```text
resolve: pass
build: fail
lint: fail
 tests: fail
```

The current failure is reproducible and narrower than the earlier generic status suggested. Valdi's Bazel action asks macOS to execute:

```text
env -i DEVELOPER_DIR=${DEVELOPER_DIR:-} xcrun ...
```

Bazel's Xcode provider resolves `/Applications/Xcode Beta.app/Contents/Developer`, but the unquoted generated shell expansion leaves `Beta.app/Contents/Developer` as a separate command. The result is `env: Beta.app/Contents/Developer: No such file or directory` before the Android module can compile. The remaining lint failure is independent (`files not formatted`); tests cannot execute because their targets fail to build. A permanent fix needs a Valdi/apple_support quoting patch or a password-authorized system Xcode path change, neither of which is being hidden as a passing result.

## Recommended order

1. Keep Flutter as the current parity/shipping control.
2. Finish the existing React Native Android path and fix the iOS compiler environment.
3. Add one real native function to Lynx and run its Android host.
4. Complete Valdi's clean Android build and test gate.
5. Compare the four on the same BLE/native adapter rather than on more UI scaffolds.

The spike deliberately excludes Tauri, Dioxus, Crepuscularity, Electrobun, Compose, Makepad, Swift, and Web/Moonshine. They are not relevant to this focused mobile decision yet.
