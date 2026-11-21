# ADR 0002: Read and write the Flutter app's state in place

**Status:** accepted (2026-10-06), verified by `Tools/dev/migration-e2e.sh`

**Context.** The native app must ship as an update over the Flutter app without users noticing.

**Decision.** No copy-based migration. The native app uses the Flutter app's storage directly:

| State | Flutter | Native |
|---|---|---|
| Firebase session | FlutterFire → native Firebase iOS SDK keychain item | same SDK, same Firebase app config: picked up as-is |
| Preferences | `shared_preferences` → `UserDefaults.standard`, key prefix `flutter.` | `OmiPersistence.Preferences` reads/writes the same `flutter.<key>` names |
| Onboarding progress | `flutter.onboardingCompleted` | honored by `SessionStore.restore()` |

**Consequences.**
- Zero migration code paths that can half-fail; downgrade to the Flutter build keeps working.
- Key names stay identical to the Android (Flutter) app, which helps parity.
- Native-only keys must not use the `flutter.` prefix (`omi.` instead).

**Evidence (P1).** Flutter dev build signed in through the real local-dev path, native build
installed over it without uninstall: native resumed the same Firebase session (emulator
`lastLoginAt` unchanged) and landed in `onboarding` / `ready` matching `flutter.onboardingCompleted`.
Screenshots: `docs/p1-migration.png`. Flutter-side spike patch: `Tools/dev/flutter-migration-autologin.patch`.

**Still to cover later:** `flutter_secure_storage` items, `wals.json` offline audio (P3), paired
device ids (P3), App Group keys for widgets (P6).
