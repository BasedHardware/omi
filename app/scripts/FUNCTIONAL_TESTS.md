# Functional Tests

This repository includes a local Maestro-based functional smoke suite for the Omi mobile app. The suite is designed for maintainers to run against a real phone while validating the highest-risk user flows from issue `#3857`.

## Coverage

The current suite covers:

- onboarding entry and consent-sheet interactions
- home tab navigation across conversations, action items, memories, and apps
- chat entry from the home screen
- settings drawer open/close
- phone recording start/stop smoke checks

The suite intentionally uses stable `Semantics` identifiers exposed by the Flutter app instead of localized button text, so the flows remain usable across UI copy changes.

## Preconditions

- Install [Maestro](https://maestro.dev/).
- Build and install the Omi app on a connected device or running emulator.
- Sign in once before running the home/navigation/recording flows.
- Grant microphone permissions before running the recording flow.
- Keep an Omi device nearby if you want to extend the suite with device-pairing flows.

Default bundle IDs used by this repository:

- Android dev: `com.friend.ios.dev`
- Android prod: `com.friend.ios`
- iOS: `com.friend-app-with-wearable.ios12`

## Running

From the app workspace:

```powershell
Set-Location .\app
.\scripts\run_functional_tests.ps1
```

Common overrides:

```powershell
.\scripts\run_functional_tests.ps1 -AppId com.friend.ios
.\scripts\run_functional_tests.ps1 -ReportsDir .\test-results\functional
.\scripts\run_functional_tests.ps1 -FlowFilter recording
.\scripts\run_functional_tests.ps1 -StopOnFailure
```

## Reports

Each run writes:

- per-flow raw Maestro logs
- `functional-test-results.json`
- `functional-test-results.md`

These artifacts make it straightforward to attach evidence to a PR comment or share failures with maintainers without rerunning the whole suite blindly.
