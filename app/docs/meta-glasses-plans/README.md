# Meta Glasses — Addon Plans (for Codex)

Nine self-contained plans to extend the Meta Wearables (DAT) integration. Each
file is executable on its own; do one per PR/branch. Ordered by leverage.

| # | Plan | Size | Depends on |
|---|------|------|-----------|
| 01 | [Thermal & hinge safety](01-thermal-hinge-safety.md) | S | — |
| 02 | [Pause/resume the photo session](02-pause-resume-session.md) | S | 01 (shares lifecycle) |
| 03 | [Ray-Ban Display on-lens UI](03-display-access-ui.md) | M | — |
| 04 | [Continuous vision via frame stream](04-continuous-vision-frames.md) | L | 02 |
| 05 | [First-class onboarding step](05-onboarding-step.md) | M | — |
| 06 | [Mock Device Kit integration tests](06-mock-device-tests.md) | M | — |
| 07 | [Contract-test the new surface](07-contract-test-coverage.md) | S | — |
| 08 | [Dedupe SwiftProtobuf](08-dedupe-swiftprotobuf.md) | M | — |
| 09 | [Android parity](09-android-parity.md) | L | — |

## Shared constraints — apply to EVERY plan

Read `app/AGENTS.md` (§Meta Wearables, §Coding Practices) and `../AGENTS.md` first. Non-negotiable:

- **Verify every DAT API before using it.** `grep 'func <name>' $SP/*.xcframework/**/arm64-apple-ios.swiftinterface` where `$SP=<derivedData>/SourcePackages/checkouts/meta-wearables-dat-ios`. Never invent methods.
- **New plugin method = 4 layers in sync**: facade `third_party/meta_wearables_dat_flutter/lib/meta_wearables_dat_flutter.dart` → `lib/src/meta_wearables_dat_platform_interface.dart` → `lib/src/meta_wearables_dat_method_channel.dart` → native `ios/.../MetaWearablesDatPlugin.swift` (+ MetaSessionManager where relevant). A Dart-only add throws `MissingPluginException` at runtime.
- **App layering**: `MetaWearablesService` (`lib/services/devices/meta_wearables_service.dart`) → `MetaWearablesProvider` (`lib/providers/meta_wearables_provider.dart`, registered in `lib/main.dart` via `ChangeNotifierProxyProvider<CaptureProvider, MetaWearablesProvider>`) → pages (`lib/pages/meta_wearables/meta_glasses_page.dart`, `lib/pages/devices/devices_page.dart`).
- **Sessions target only link-connected uuids** — reuse `MetaWearablesProvider._sessionTargetUuid`; never pass an unlinked/shadow uuid.
- **iOS 17 floor**: keep `ios/Flutter/Flutter.podspec` `deployment_target = '17.0'` (it resets to 13.0 on `pub get`/clean).
- **Debug-only screens gate on `kDebugMode`**, never `!kReleaseMode`.
- **l10n**: user-facing strings via `context.l10n.*`; add keys to all `lib/l10n/app_*.arb` (49 locales) with real translations; `flutter gen-l10n` must report 0 untranslated.
- **No purple** anywhere in UI (off-brand). White/neutral accents.
- **Format**: `dart format --line-length 120`. Swift/Rust per repo hooks.
- **Green gate before proposing merge**: `flutter analyze` (0 errors), `flutter test test/unit/omi4meta_reconstruction_contract_test.dart test/unit/meta_glasses_device_sanitize_test.dart`, and extend those tests for new surface (see plan 07 pattern).
- **Build/sign/install** for device verification: see `~/.claude` memory `omi4meta-ios-build-install` or `app/AGENTS.md`. Bundle `dev.moni11811.omi`, EddyPhone `2649C7E8-7E64-501B-9108-8BC6038B8C2F`. After any `--dart-define` verification build, reinstall a normal build.

## Ground truth captured 2026-07-03 (don't re-derive, but re-verify if SDK bumped)

- **No battery percentage API.** DAT surfaces only `batteryCritical`/`thermalCritical`/`thermalEmergency`/`hingesClosed` as session-error signals. Native currently maps `thermalCritical`, `hingesClosed`, `deviceDisconnected` (`MetaSessionManager.swift` ~L531). `SessionError.isThermalCritical` / `isHingesClosed` exist in `lib/src/models/dat_error.dart`.
- Provider already subscribes to `streamSessionErrorStream()` / `deviceSessionErrorStream()` (`_streamErrorSub` / `_deviceErrorSub`).
- `pauseStreamSession` / `resumeStreamSession` / `videoFramesStream` / `enableMockDevice` / `pairMockRayBanMeta` / `captureStreamFrame` all exist on the facade.
- DAT SDK is v0.8 in `SourcePackages`; the vendored Flutter wrapper is locally patched (linkState, openFirmwareUpdate, openDATGlassesAppUpdate).
