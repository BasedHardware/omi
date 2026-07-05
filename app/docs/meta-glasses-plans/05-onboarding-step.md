# 05 — First-class onboarding step

## Goal
Make Meta glasses discoverable during first-run onboarding, not only via the
connect page + guide. A new user should be offered "Connect Meta Glasses" in the
same flow they'd pick an Omi device.

## Grounding
- Onboarding lives in `lib/pages/onboarding/` — key files: `wrapper.dart` (step controller; note `kFindDevicesPage = 8`), `device_selection.dart`, `interactive_device_onboarding/`, `find_device/`.
- Existing entry points already built: `ConnectionGuideSheet` (has a Meta Glasses card), `MetaGlassesPage`, and `connect.dart`'s Meta card.
- Provider is app-level (`ChangeNotifierProxyProvider` in `main.dart`) so onboarding can read `MetaWearablesProvider` directly.

## Steps
1. In the device-selection / interactive onboarding step, add a "Meta Glasses" option alongside Omi devices, using `Assets.images.omiGlass.path` (same artwork used elsewhere) and `context.l10n.metaGlasses`.
2. Tapping it pushes `MetaGlassesPage` (registration + capture there already works). On successful registration (`MetaWearablesProvider.isRegistered && hasLinkedDevices`), advance the onboarding controller past the device step (mirror how the Omi path calls `goNext`).
3. If the user has glasses linked but skips Omi, ensure onboarding still completes (don't hard-require a BLE device). Check `wrapper.dart` completion gating and allow "glasses only".
4. Respect existing consent/permission gates in `lib/mobile/mobile_app.dart` — the new step sits inside `OnboardingWrapper`, after consent, same as today.
5. Analytics: fire the existing device-onboarding analytics events with a `meta_glasses` label where applicable.

## Tests
- Widget/unit test that the onboarding device step renders a Meta Glasses option and that `hasLinkedDevices` satisfies step completion (mock the provider).
- Contract test: onboarding references `MetaGlassesPage`/`MetaWearablesProvider`.

## Acceptance
- Fresh onboarding offers Meta Glasses; registering there completes onboarding without requiring a BLE Omi device.
- Existing Omi onboarding path unchanged.
- Analyze clean; tests green; l10n reuses existing keys (no English left in non-EN ARBs).
