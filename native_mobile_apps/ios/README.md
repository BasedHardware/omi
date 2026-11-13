# Omi for iOS, native (SwiftUI)

A native SwiftUI rewrite of the Omi iOS app (`app/` in BasedHardware/omi). Same backend, same API
contract, same Firebase project and the same on-device state, so it can install over the Flutter
app and keep the user signed in with their paired Omi and offline recordings.

Status: a working app, not yet at full parity with Flutter. See `docs/PARITY-AUDIT.md` for what is
missing, partial or native-only, and `docs/STRUCTURE.md` for where every screen and setting lives.

## Layout
- `App/` the app shell (tabs, header, routing, composition root)
- `Packages/` SwiftPM packages: `OmiCore` (models), `OmiNetwork` (API client, generated DTOs),
  `OmiPersistence`, `OmiService` (stores and logic), `OmiDesign` (tokens, strings),
  `OmiFeatures` (one module per feature; features never import each other)
- `Extensions/` widgets, Live Activity, notification service; `Watch/` the watch recorder
- `Tools/` code generation (strings from the Flutter ARB files, API types from the OpenAPI spec)
  and dev helpers; `docs/` structure, parity, ADRs, device testing

## Build
Requires Xcode 26+, XcodeGen and SwiftLint.

```
cp Config/Secrets.xcconfig.example Config/Secrets.xcconfig   # team, bundle id, backend host
xcodegen generate
make test        # swift test for every package
open Omi.xcodeproj
```

Release builds use Omi's production Firebase file: inside the Omi repository the Flutter app's
(`app/setup/release-firebase/GoogleService-Info.prod.plist`); a separate checkout sets
`OMI_FIREBASE_PROD_PLIST` in `Config/Secrets.xcconfig` to its copy. Debug builds use the local Firebase
emulator config.

To run against a local backend, start the dev harness from the main repo (`make dev-up`) and see
`docs/DEVICE_TESTING.md`. Two optional backend changes the app uses are in `docs/backend-patches/`.

## Strings
`Tools/l10n/native.json` holds the native-only keys; `make strings OMI_UPSTREAM=<path to omi repo>`
merges them with the Flutter translations into `Localizable.xcstrings`.

## License
MIT, as the main Omi repository.
