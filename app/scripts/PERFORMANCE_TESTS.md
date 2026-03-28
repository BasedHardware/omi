# Omi Performance Test Runner

This document describes the Windows runner for the existing Flutter integration performance tests in `app/integration_test/`.

## Coverage

The runner executes these profile-mode tests:

- `integration_test/app_performance_test.dart`
- `integration_test/animation_performance_test.dart`
- `integration_test/shimmer_cpu_test.dart`
- `integration_test/widget_rebuild_profiling_test.dart`

These cover the issue goals around responsiveness, frame pacing, CPU churn, and widget rebuild overhead. The integration tests already contain the app-specific assertions and timing output; the runner adds orchestration and report generation.

## Prerequisites

- Windows PowerShell
- `flutter` available in `PATH`
- `adb` available in `PATH`
- A connected Android device or emulator
- The app dependencies already installed via the normal app setup flow

## Run

From the `app/` directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_performance_tests.ps1
```

Common options:

```powershell
# Target a specific device
powershell -ExecutionPolicy Bypass -File .\scripts\run_performance_tests.ps1 -DeviceId emulator-5554

# Skip the APK rebuild when you already built a profile binary
powershell -ExecutionPolicy Bypass -File .\scripts\run_performance_tests.ps1 -SkipBuild

# Continue even if one test fails
powershell -ExecutionPolicy Bypass -File .\scripts\run_performance_tests.ps1 -KeepGoing
```

## Outputs

Each run creates a timestamped folder under `app/test_reports/performance/` containing:

- `summary.json`: machine-readable run metadata and per-test status
- `summary.md`: human-readable report for maintainers
- `<test-name>.log`: raw stdout/stderr capture for each integration test

This gives maintainers a repeatable local workflow that can run for short validation loops or longer soak sessions while keeping logs and summaries in one place.
