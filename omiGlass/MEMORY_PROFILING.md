# Memory Profiling Workflow — omi/omiGlass

## Overview

This guide walks through identifying live memory leaks in the OmiGlass React Native app using the built-in `MemoryProfilerOverlay` and React Native DevTools.

## Quick Start

The profiling overlay is **DEV-only** — it auto-appears in the top-right corner when running in development mode. No code changes needed.

### Step 1: Enable Performance Memory API

For the profiler to report JS heap metrics, you need `performance.memory` exposed:

**Android** — add to `android/app/src/main/java/com/.../MainApplication.java`:
```java
import com.facebook.hermes.instrumentation.HermesSamplingProfiler;
// In onCreate():
WebView.setWebContentsDebuggingEnabled(true);
```

Or in Metro config, ensure Hermes is enabled (default for Expo).

**iOS** — in Xcode, enable the Safari Web Inspector for the JS context.

### Step 2: Open React Native DevTools

```bash
# Start Metro
npx expo start

# Press 'j' in Metro terminal to open DevTools
# Or: shake device → "Open DevTools"
```

### Step 3: Take Heap Snapshots

In React DevTools → **Memory** tab:

1. **Baseline snapshot**: Take before connecting to BLE device
2. **Connected snapshot**: Connect to OMI Glass, wait 30s, take another
3. **After navigation**: Navigate away from DeviceView, wait 30s, take another
4. **Compare**: Click "Comparison" view between snapshots 2 and 3

### Step 4: Use the Overlay

The overlay shows:
- **Current heap size** (MB) — green < 100MB, orange 100-200MB, red > 200MB
- **Growth since start** — total heap change
- **Growth rate** — MB/min (should trend to 0 after initial load)
- **⚠️ Leak warning** — appears after 3+ consecutive growth periods exceeding 5MB

Tap the overlay to expand for full details.

### Step 5: Console Profiling

From any debugging session (Chrome remote debugging, Metro console):

```javascript
// Take an immediate memory snapshot
global.__takeMemSnapshot()

// Example: take snapshots before/after a user flow
global.__takeMemSnapshot()   // Before
// ... do user flow ...
global.__takeMemSnapshot()   // After — compare heap sizes
```

## Leak Detection Checklist

### BLE Subscriptions (Fixed)

- [x] `usePhotos` hook: BLE event listener + stopNotifications cleanup
- [x] `useDevice` hook: GATT disconnect + ongattserverdisconnected cleanup
- [x] Race condition: `cancelled` flag after every `await` in async BLE setup

### Unbounded Growth (Fixed)

- [x] `processedPhotos` ref: capped to last 100 items
- [x] `InvalidateSync.stop()` called on unmount
- [x] `AudioContext` properly closed via `stopAudio()` on unmount

### Still Monitor

- [ ] `photos` state array grows with each photo (every ~5s) — not capped at state level
- [ ] `Agent.#photos` array accumulates descriptions forever — consider LRU eviction
- [ ] Image `toBase64Image()` creates data URLs that may not be GC'd while in ScrollView

## Profiling Workflow

### Flow 1: BLE Connect/Disconnect Cycle

1. Start app, observe baseline heap (~20-40 MB)
2. Connect to OMI Glass → heap should rise and stabilize (~60-80 MB)
3. Disconnect → heap should drop back toward baseline
4. Reconnect → heap should return to same level (not higher)
5. **If heap keeps growing on each cycle → BLE subscription leak**

### Flow 2: Photo Accumulation

1. Connect and let photos stream for 5+ minutes
2. Watch heap growth rate in overlay
3. After ~100 photos, heap should plateau (capped processing)
4. **If heap grows linearly with photo count → images not being GC'd**

### Flow 3: Component Mount/Unmount

1. Connect to device (DeviceView mounts)
2. Disconnect (DeviceView unmounts)
3. Take heap snapshot before and after
4. **If heap doesn't decrease after unmount → effect cleanup leak**

## Native Memory Profiling

### iOS (Xcode Instruments)

1. Open `omiGlass.xcworkspace` in Xcode
2. Product → Profile (⌘I)
3. Select **Allocations** instrument
4. Record while running the app
5. Look for growing `VM` regions or un-freed `CFData` objects

### Android (Android Studio)

1. Open `omiGlass/android` in Android Studio
2. Run → Profile
3. Select **Memory** tab
4. Take heap dumps before/after flows
5. Look for growing `byte[]` arrays (image data) or `NativeAllocationRegistry` objects

## Key Metrics to Watch

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| JS Heap at idle | < 60 MB | 60-120 MB | > 120 MB |
| Growth after disconnect | < 2 MB | 2-10 MB | > 10 MB |
| Growth rate (steady state) | < 0.5 MB/min | 0.5-2 MB/min | > 2 MB/min |
| RSS delta per connect cycle | < 5 MB | 5-20 MB | > 20 MB |

## Attribution

Based on React Native Best Practices (Callstack) memory profiling guidelines.
