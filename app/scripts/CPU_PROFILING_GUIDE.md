# Android CPU Profiling Guide for Omi App

## Overview

This guide explains how to measure CPU usage on Android devices to identify battery drain issues.

## Prerequisites

1. **ADB installed**: `brew install android-platform-tools` (macOS)
2. **Android device connected** with USB debugging enabled
3. **App built in profile or release mode** (avoid debug for CPU measurement)

## Quick Start

### 1. Build Profile APK

```bash
cd app
flutter build apk --flavor dev --profile --target-platform android-arm64
```

Output: `build/app/outputs/flutter-apk/app-dev-profile.apk`

### 2. Install and Run

```bash
adb install build/app/outputs/flutter-apk/app-dev-profile.apk
# Or run directly:
flutter run --profile --flavor dev
```

### 3. Measure CPU

```bash
./scripts/measure_cpu_android.sh -p com.friend.ios.dev -n 15 -d 2 -o /tmp/omi_cpu_baseline.csv
```

## Measurement Methods

### Method 1: Single Measurement Script (Recommended)

```bash
./scripts/measure_cpu_android.sh -p <package> [-s <device>] [-n <samples>] [-d <delay>] [-o <csv>]

# Examples:
./scripts/measure_cpu_android.sh -p com.friend.ios.dev -n 15 -d 2
./scripts/measure_cpu_android.sh -p com.friend.ios.dev -n 20 -d 1 -o /tmp/omi_cpu_idle.csv
```

### Method 2: Compare Two Builds

```bash
./scripts/compare_cpu_builds.sh \
  build/app/outputs/flutter-apk/app-A.apk "version-A" \
  build/app/outputs/flutter-apk/app-B.apk "version-B" \
  -p com.friend.ios.dev -n 15 -d 2
```

### Method 3: Manual Measurement

```bash
# Single sample
adb shell "top -b -n 1 | grep com.friend.ios.dev"

# Continuous monitoring
adb shell "top -d 2 | grep --line-buffered com.friend.ios.dev"
```

## Understanding Results

| CPU % | Interpretation |
|-------|----------------|
| 0-10% | Idle - excellent |
| 10-30% | Light activity - good |
| 30-50% | Moderate - acceptable for active use |
| 50-100% | High - potential battery drain |
| >100% | Very high - using multiple cores, investigate! |

**Note**: CPU >100% means the app is using more than one CPU core. Use median CPU across samples, not single spikes.

## Common Battery Drain Causes

### 1. Shimmer Animations
- **Symptom**: High CPU even when idle
- **Cause**: `Shimmer.fromColors` runs continuous animation
- **Fix**: Replace with static skeleton or use `AnimatedOpacity`

### 2. Unnecessary Widget Rebuilds
- **Symptom**: CPU spikes on state changes
- **Cause**: Using `Consumer` instead of `Selector`
- **Fix**: Use `Selector` to listen only to specific fields

### 3. Background Timers
- **Symptom**: Constant CPU usage
- **Cause**: Timers running when not needed
- **Fix**: Cancel timers when widget disposed or app backgrounded

## A/B Testing Workflow

To compare CPU impact of a change:

```bash
# 1. Build baseline APK
git checkout main
flutter build apk --flavor dev --profile
cp build/app/outputs/flutter-apk/app-dev-profile.apk /tmp/baseline.apk

# 2. Build changed APK
git checkout feature-branch
flutter build apk --flavor dev --profile
cp build/app/outputs/flutter-apk/app-dev-profile.apk /tmp/feature.apk

# 3. Compare
./scripts/compare_cpu_builds.sh /tmp/baseline.apk "baseline" /tmp/feature.apk "feature" -p com.friend.ios.dev
```

## Findings Log

### 2026-01-29: Shimmer CPU Impact

| Scenario | CPU Usage |
|----------|-----------|
| WITH Shimmer widget | ~135% |
| WITHOUT Shimmer widget | ~41% |

**Conclusion**: Single Shimmer widget adds ~94% CPU overhead.

## Troubleshooting

### "App not in top CPU users"
- App might be in background or screen off
- Ensure app is in foreground and screen is on

### Inconsistent readings
- Wait 10s after app launch before measuring
- Ensure no other heavy apps running
- Keep device plugged in to avoid thermal throttling

### `dumpsys cpuinfo` shows 0%
- Use `top` command instead (more accurate for Flutter apps)
- The scripts use `top` by default

## Related Files

- `scripts/measure_cpu_android.sh` - Single measurement script (median-based)
- `scripts/compare_cpu_builds.sh` - A/B comparison script (median-based)
- `integration_test/shimmer_cpu_test.dart` - Automated shimmer test
