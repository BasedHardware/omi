# 01 — Thermal & hinge safety

## Goal
React to the glasses' health signals instead of ignoring them: auto-pause
capture on thermal-critical, tell the user when the glasses fold (hinges
closed) or overheat, and clear the warning when capture recovers.

> **Reality check:** DAT exposes **no battery percentage**. Do NOT add a battery
> gauge — there is no API. This plan is about the thermal/hinge/disconnect
> *session-error* signals that already reach Dart.

## Grounding (verified)
- `SessionError.isThermalCritical`, `SessionError.isHingesClosed` in `third_party/meta_wearables_dat_flutter/lib/src/models/dat_error.dart`.
- Native emits codes `thermalCritical`, `hingesClosed`, `deviceDisconnected` (`ios/.../MetaSessionManager.swift` ~L531).
- Provider already listens: `_streamErrorSub = MetaWearablesDat.streamSessionErrorStream()...` and `_deviceErrorSub = ...deviceSessionErrorStream()` in `lib/providers/meta_wearables_provider.dart` (~L263/L270). They currently just set `lastError`.

## Steps
1. In `MetaWearablesProvider` add typed state: `enum MetaGlassesHealth { ok, overheating, foldedClosed }` and a field `MetaGlassesHealth health = MetaGlassesHealth.ok;`.
2. In the `_streamErrorSub`/`_deviceErrorSub` handlers, inspect the error. If it is a `SessionError` with `isThermalCritical` → set `health = overheating`; `isHingesClosed` → `foldedClosed`. Keep setting `lastError` too. `notifyListeners()`.
3. On `thermalCritical`: call the existing `_stopPhotoLoop()` (pause camera) but do **not** set `_manualStopRequested` — this is an automatic, recoverable pause. Keep mic capture running. Add an internal `_thermalPaused` flag.
4. Recovery: there is no "cleared" event. On the next successful `capturePhoto()` or a `deviceSessionStateStream` transition back to `started`, set `health = ok`, `_thermalPaused = false`, and restart the photo loop if `captureMode == cameraAndMic`. Add a periodic (e.g. 20s) retry while `_thermalPaused`.
5. UI: in `meta_glasses_page.dart` show a dismissible warning row above the capture button when `health != ok` (icon `Icons.thermostat`/`Icons.visibility_off`, `Colors.orangeAccent`, no purple). In `devices_page.dart` glasses card, replace the status line with the health warning when `health != ok`.
6. l10n keys (all 49 locales): `metaGlassesOverheating` ("Glasses are cooling down — capture paused"), `metaGlassesFolded` ("Unfold your glasses to keep capturing").

## Tests
- Unit-test the error→health mapping with a fake error object exposing `isThermalCritical`/`isHingesClosed` (extend `test/unit/meta_glasses_device_sanitize_test.dart` or new `test/unit/meta_glasses_health_test.dart`).
- Contract test (plan 07 pattern): assert provider contains `MetaGlassesHealth`, `isThermalCritical`, and that thermal pause does not set `_manualStopRequested`.

## Acceptance
- Overheat during capture → photo loop pauses, mic keeps going, orange banner shows; when it recovers, photos resume automatically without a manual restart.
- Folding the glasses shows the fold hint. No battery-percentage UI anywhere.
- `flutter analyze` clean; contract + health tests green; l10n 0 untranslated.
