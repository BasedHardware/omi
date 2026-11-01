# Onboarding polish evidence

Light theme, 393×852 logical pixels at 3×, Flutter 3.44.5. App FontManifest fonts, SF Pro Display for iOS and Flutter SDK Roboto for Android. Every PNG was opened and visually inspected after generation; no box glyphs, overflow stripes, or clipped primary actions.

Reproduce from `app/`:

```sh
ONB_POLISH_RENDER=1 flutter test test/widgets/onboarding_polish_test.dart test/providers/onboarding_provider_pairing_presentation_test.dart
```

Watch is iOS only. The survey includes its initial and final scroll positions at 2.0 text scale. Connect uses inert providers seeded with the same closed failure enum as production. Nearby-devices/location reasons are Android-only runtime cases; their iOS images exercise the complete copy mapping, not iOS permission detection. Stale-bond detection currently uses the service's existing iOS latch. A swallowed connection error has only combined reachability guidance.

| Screen/state | iOS | Android |
| --- | --- | --- |
| Watch instructions | [PNG](001-mobile-ios-watch.png) | — |
| Find-us, default text | [PNG](009-mobile-ios-find-us.png) | [PNG](019-mobile-android-find-us.png) |
| Find-us, 2.0 text | [PNG](010-mobile-ios-find-us-large.png) | [PNG](020-mobile-android-find-us-large.png) |
| Find-us, 2.0 text, scrolled to end | [PNG](011-mobile-ios-find-us-large-end.png) | [PNG](021-mobile-android-find-us-large-end.png) |
| Connect: `bluetooth_off` | [PNG](002-mobile-ios-connect-bluetooth-off.png) | [PNG](012-mobile-android-connect-bluetooth-off.png) |
| Connect: `bluetooth_permission_denied` | [PNG](003-mobile-ios-connect-bluetooth-permission-denied.png) | [PNG](013-mobile-android-connect-bluetooth-permission-denied.png) |
| Connect: `nearby_devices_denied` | [PNG](004-mobile-ios-connect-nearby-devices-denied.png) | [PNG](014-mobile-android-connect-nearby-devices-denied.png) |
| Connect: `location_permission_missing` | [PNG](005-mobile-ios-connect-location-permission-missing.png) | [PNG](015-mobile-android-connect-location-permission-missing.png) |
| Connect: `not_found_or_dropped` | [PNG](006-mobile-ios-connect-not-found-or-dropped.png) | [PNG](016-mobile-android-connect-not-found-or-dropped.png) |
| Connect: `stale_bond` | [PNG](007-mobile-ios-connect-stale-bond.png) | [PNG](017-mobile-android-connect-stale-bond.png) |
| Connect: `unknown` | [PNG](008-mobile-ios-connect-unknown.png) | [PNG](018-mobile-android-connect-unknown.png) |

| Empty scan after 10 seconds (real provider, scrolled to instructions) | [PNG](022-mobile-ios-connect-empty-scan.png) | [PNG](023-mobile-android-connect-empty-scan.png) |

The empty-scan images execute the production OnboardingProvider scan timer with inert device I/O and an offline connectivity mock. Tests assert No Omi Found, its instructions, Contact Support, existing Device Scan Empty telemetry, and no Device Connect Failure Shown. They also verify discovered and saved-device reachability-card clearing; Bluetooth-off and unauthorized exceptions take precedence over the stale-bond latch.
