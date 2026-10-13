# Onboarding polish evidence

Light theme, 393×852 logical pixels at 3×, Flutter 3.44.5. App FontManifest fonts, SF Pro Display for iOS and Flutter SDK Roboto for Android. Every PNG was opened and visually inspected after generation; no box glyphs, overflow stripes, or clipped primary actions.

Reproduce from `app/`:

```sh
ONB_POLISH_RENDER=1 flutter test test/widgets/onboarding_polish_test.dart
```

Watch is iOS only. The survey includes its initial and final scroll positions at 2.0 text scale. Connect uses inert providers seeded with the same closed failure enum as production. Nearby-devices/location reasons are Android-only runtime cases; their iOS images exercise the complete copy mapping, not iOS permission detection. Stale-bond detection currently uses the service's existing iOS latch. A swallowed connection error has only combined reachability guidance.

| Screen/state | iOS | Android |
| --- | --- | --- |
| Watch instructions | [PNG](ios-watch.png) | — |
| Find-us, default text | [PNG](ios-find-us.png) | [PNG](android-find-us.png) |
| Find-us, 2.0 text | [PNG](ios-find-us-large.png) | [PNG](android-find-us-large.png) |
| Find-us, 2.0 text, scrolled to end | [PNG](ios-find-us-large-end.png) | [PNG](android-find-us-large-end.png) |
| Connect: `bluetooth_off` | [PNG](ios-connect-bluetooth_off.png) | [PNG](android-connect-bluetooth_off.png) |
| Connect: `bluetooth_permission_denied` | [PNG](ios-connect-bluetooth_permission_denied.png) | [PNG](android-connect-bluetooth_permission_denied.png) |
| Connect: `nearby_devices_denied` | [PNG](ios-connect-nearby_devices_denied.png) | [PNG](android-connect-nearby_devices_denied.png) |
| Connect: `location_permission_missing` | [PNG](ios-connect-location_permission_missing.png) | [PNG](android-connect-location_permission_missing.png) |
| Connect: `not_found_or_dropped` | [PNG](ios-connect-not_found_or_dropped.png) | [PNG](android-connect-not_found_or_dropped.png) |
| Connect: `stale_bond` | [PNG](ios-connect-stale_bond.png) | [PNG](android-connect-stale_bond.png) |
| Connect: `unknown` | [PNG](ios-connect-unknown.png) | [PNG](android-connect-unknown.png) |
