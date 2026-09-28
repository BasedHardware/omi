# app/ — Swift cross-platform client

Rewrite-branch area guide: the React Native client is replaced by one
SwiftPM package (`../Package.swift`, tools 6.1). `CNativeCore` compiles the
C++ `../native-core/` middleware in place; `OmiKit` is the shared
platform-neutral core (Skip transpiles it to Kotlin for Android); `OmiUI`
is the shared SwiftUI (SkipUI-compatible) surface layer. Root rules:
[`../AGENTS.md`](../AGENTS.md).

## Layout

- `Sources/OmiKit/` — platform-neutral core, by area:
  - `Wire/` — backend wire codecs and request/response models.
  - `Backend/` — backend clients and cursor envelopes.
  - `Session/` — account, origin, and session state.
  - `Devices/` — BLE device state and connection flows.
  - `Timeline/` — merged timeline and pagination semantics.
  - Foundation files: `Models.swift`, `Origin.swift`, `Routes.swift`,
    `Transport.swift` (native authenticated transport),
    `BackendError.swift`, `Policy.swift` (the only consumer of the
    CNativeCore C ABI).
- `Sources/OmiUI/` — shared SwiftUI surfaces (currently `RootView.swift`,
  `Tokens.swift`; pages are port pending from the v5 behavior spec in
  `../docs/mobile.md` / `../docs/desktop-app.md`).
- `Tests/OmiKitTests/`, `Tests/OmiUITests/` — `swift test` targets
  (in the gate via `bun run swift:test`).
- `Platforms/` — per-platform host entry points (iOS / Android / macOS /
  Windows). Host projects live here (`README` or `project.yml` per
  platform); not yet created — port pending.

## Commands

```sh
swift build          # compiles all targets, runs the Skip skipstone plugin
swift test           # OmiKitTests + OmiUITests (gate: bun run swift:test)
```

Both need a macOS host with the Swift 6 toolchain (Xcode stable).
For parallel work use an isolated scratch build dir so you don't collide
with other build outputs:

```sh
swift build --scratch-path .build-<task>
```

Build output — including the Skip Kotlin output under
`.build/plugins/outputs/` — is generated; never commit it
(`check-boundaries` bans `.build`).

## Skip transpiler rules (discovered so far)

- Consumer code imports **SwiftUI only**. SkipUI is the transpiler's
  implementation detail — never `import SkipUI` in OmiKit/OmiUI sources.
- Never use SkipUI property-wrapper attributes.
- Avoid `URLError`, `Character.isNumber`, and `String.allSatisfy` (no
  Kotlin equivalent / unsupported mapping).
- Qualify nested Foundation enums, e.g. `DateFormatter.Style.medium`.
- No extensions adding constructors to SwiftUI/Foundation types.
- Static `Color` tokens need `nonisolated(unsafe)`.
- Guard C imports with `#if !SKIP` — the C ABI (`CNativeCore`) does not
  exist on the Kotlin side; native-core is consumed **only** through the
  `Policy` facade, which owns those guards.

## Platform hosts

Each `Platforms/<platform>/` carries its own entry point (README or
`project.yml`) and owns only bootstrap — material/window behavior,
credential-store-backed `CredentialStoring` implementations, and platform
permissions. All product behavior lives in OmiKit + OmiUI. The macOS
desktop and mobile behavior specs are `../docs/desktop-app.md` and
`../docs/mobile.md`.
