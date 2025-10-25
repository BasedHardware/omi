# Quick Start: Run Omi Watch App

## Xcode Project Settings

**Project**: `Runner.xcodeproj`
**Target**: `omiWatchApp`
**Scheme**: `omiWatchApp`
**Current Team**: `9536L8KLMP`
**Bundle ID**: `com.friend-app-with-wearable.ios12.watchapp`
**Code Signing**: Automatic (Apple Development)

## Option 1: Command Line (Simulator Only - No Team Needed)

```bash
# 1. Build the app (code signing disabled for simulator)
cd /Users/eulices/omi-fork-4
./build-watch.sh

# 2. Open Watch Simulator
open -a Simulator

# 3. Wait for simulator to boot, then install
xcrun simctl install booted app/ios/build/Debug-watchsimulator/omiWatchApp.app

# 4. Launch the app
xcrun simctl launch booted com.friend-app-with-wearable.ios12.watchapp
```

## Option 2: Xcode GUI (Simulator or Device)

```bash
cd /Users/eulices/omi-fork-4/app/ios
open Runner.xcodeproj
```

### In Xcode:

1. **Select Scheme**: Click scheme dropdown (top left) → Choose `omiWatchApp`
2. **Select Destination**:
   - For **simulator**: Choose any watchOS 26+ simulator
   - For **device**: Connect your Apple Watch and select it
3. **Set Team** (if building for device):
   - Select `omiWatchApp` target in project navigator
   - Go to "Signing & Capabilities" tab
   - Under "Team", select your Apple Developer team
   - Current team in project: `9536L8KLMP`
4. **Run**: Click Run button (⌘R) or Product → Run

### If You Need a Different Team:

If the current team (`9536L8KLMP`) doesn't work for you:
1. Click on `omiWatchApp` target
2. Go to "Signing & Capabilities"
3. Change "Team" to your own Apple Developer team
4. Xcode will automatically update the provisioning profile

## Verify Glass Effects

Once running, you should see:
- ✨ Translucent glass button in the center
- ✨ Glass status capsule at bottom ("Tap to Record")
- ✨ Ripple animations with glass effect when recording

## Troubleshooting

### Simulator doesn't show glass effects
**Solution**: Make sure you're using watchOS 26+ simulator. Glass effects require watchOS 26.0 or later.

```bash
# List available simulators
xcrun simctl list devices watchOS
```

### Build fails with code signing error
**Solution**: The build script disables code signing for simulator builds. Make sure you're using `./build-watch.sh` for simulator testing.

### App crashes on launch
**Solution**: Check the console logs:
```bash
xcrun simctl spawn booted log stream --predicate 'processImagePath contains "omiWatchApp"'
```

## Testing Features

### Main Recording Interface
1. Tap the glass button to start recording → should see:
   - Glass material becomes interactive
   - Ripples animate outward with glass effect
   - Status changes to "Listening"
2. Tap again to stop recording

### Watch Widgets
The app includes Smart Stack widgets (currently in same target):
- Circular widget: Battery % or recording status
- Rectangular widget: Full status with icon
- Corner widget: Simple waveform indicator

Note: Widget functionality may be limited in simulator. Full widget testing requires a physical device with watchOS 26+.

## Next Steps

After simulator testing, proceed to device testing for:
- Real glass material rendering (simulator approximates but doesn't match device fidelity)
- Always-On Display transitions
- Performance and battery impact
- Haptic feedback

See [WATCHOS_GLASS_TEST_RESULTS.md](WATCHOS_GLASS_TEST_RESULTS.md) for detailed testing checklist.
