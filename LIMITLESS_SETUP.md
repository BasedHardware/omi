# Limitless Pendant Setup - Quick Reference

## Prerequisites Check

Before starting, ensure you have:

- ✅ Flutter SDK installed (`flutter --version`)
- ✅ Android Studio (for Android) OR Xcode (for iOS/macOS)
- ✅ Your Limitless pendant charged and ready

## Step-by-Step Setup

### 1. Navigate to App Directory
```bash
cd app
```

### 2. Run Setup Script

**Windows (Android):**
```bash
bash setup.sh android
```

**macOS (iOS):**
```bash
bash setup.sh ios
```

**macOS (Desktop):**
```bash
bash setup.sh macos
```

### 3. Pair Your Limitless Pendant

1. Turn on your Limitless pendant (press and hold button until LED lights up)
2. Open the OMI app
3. Go to Settings → Devices or Onboarding → Find Device
4. Tap "Scan for Devices"
5. Look for your pendant (name should contain "limitless" or "pendant")
6. Tap to connect
7. Wait for initialization (time sync + data stream enable)

### 4. Test Real-Time Transcription

1. With pendant connected, go to the Capture/Home screen
2. Start speaking - you should see real-time transcription
3. Double-press the pendant button to pause/resume

### 5. Test Offline Sync

1. Disconnect from the app (or turn off phone Bluetooth)
2. Use the pendant to record (long press to start/stop recording)
3. Reconnect to the app
4. Look for the "Sync your recordings" card
5. Tap "Sync Now" to download stored recordings

## Troubleshooting

### App Won't Build

- Check Flutter version: `flutter --version` (should be 3.35.3+)
- Run `flutter doctor` to check for issues
- Ensure you have the correct platform SDK installed

### Pendant Not Found

- Make sure Bluetooth is enabled
- Ensure pendant is powered on and in pairing mode
- Try restarting both app and pendant
- Check device name contains "limitless" or "pendant"

### Connection Fails

- Forget device in phone Bluetooth settings
- Restart app
- Ensure pendant isn't connected to another device

### No Audio/Transcription

- Check app has microphone permissions
- Verify connection status in app
- Check backend is accessible (if self-hosting)

## Next Steps

After successful setup:
- ✅ Test real-time transcription
- ✅ Test offline recording sync
- ✅ Explore customization options
- ✅ Consider self-hosting backend

For detailed information, see [LIMITLESS_MIGRATION_GUIDE.md](LIMITLESS_MIGRATION_GUIDE.md)

