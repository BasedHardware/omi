# Limitless AI Pendant to OMI Migration Guide

## Overview

Your Limitless AI pendant is **already fully supported** by OMI! No firmware changes needed - OMI communicates with your pendant using the existing Limitless Bluetooth protocol.

## Quick Start (5 minutes)

### Step 1: Build the OMI App

**For Windows (using Android):**
```bash
cd app
bash setup.sh android
```

**For macOS/iOS:**
```bash
cd app
bash setup.sh ios
```

**For macOS Desktop:**
```bash
cd app
bash setup.sh macos
```

The setup script will:
- Install Flutter dependencies
- Set up Firebase configuration
- Configure the app for development
- Build and run the app

### Step 2: Pair Your Limitless Pendant

1. **Turn on your Limitless pendant** (press and hold the button)
2. **Open the OMI app** on your device
3. **Navigate to device pairing** (usually in Settings or Onboarding)
4. **Scan for devices** - The app will automatically detect your pendant if:
   - Device name contains "limitless" or "pendant"
   - OR device advertises the Limitless service UUID: `632de001-604c-446b-a80f-7963e950f3fb`
5. **Select your pendant** from the list
6. **Connect** - The app will automatically:
   - Sync device time
   - Enable data streaming
   - Initialize the connection

### Step 3: Start Using

- **Real-time transcription**: Start speaking - audio streams to OMI backend for transcription
- **Offline recordings**: When you reconnect, stored recordings automatically sync
- **Button controls**:
  - **Double press**: Pause/Resume conversation
  - **Long press**: Device-side recording start/stop (handled by pendant)
  - **Short press**: Currently not mapped (can be customized)

## How It Works

### Architecture

```
┌─────────────────┐
│ Limitless       │
│ Pendant         │
│ (Original       │
│  Firmware)      │
└────────┬────────┘
         │ Bluetooth LE
         │ (OPUS Audio)
         ▼
┌─────────────────┐
│ OMI Flutter App │
│ (limitless_     │
│  connection.dart│
└────────┬────────┘
         │ WebSocket
         │ (Audio Data)
         ▼
┌─────────────────┐
│ OMI Backend     │
│ (FastAPI +      │
│  Deepgram STT)  │
└─────────────────┘
```

### Protocol Details

The OMI app communicates with your Limitless pendant using:

- **Service UUID**: `632de001-604c-446b-a80f-7963e950f3fb`
- **TX Characteristic**: `632de002-604c-446b-a80f-7963e950f3fb` (commands to device)
- **RX Characteristic**: `632de003-604c-446b-a80f-7963e950f3fb` (data from device)
- **Audio Codec**: OPUS at 320 frame size (16kHz, 16-bit)
- **Protocol**: Protobuf-style encoding for commands

### Key Features

1. **Real-time Streaming**: Audio streams live from pendant → app → backend
2. **Offline Sync**: Stored recordings (flash pages) sync when you reconnect
3. **Battery Monitoring**: Battery level displayed in app
4. **Button Handling**: Double-press mapped to pause/resume

## Self-Hosting the Backend (Optional)

If you want to run your own backend instead of using OMI's cloud service:

### Prerequisites

- Python 3.8+
- PostgreSQL database
- Redis instance (Upstash recommended for free tier)
- Google Cloud Project with Firebase enabled
- API keys: OpenAI, Deepgram, Pinecone

### Setup Steps

1. **Navigate to backend directory:**
   ```bash
   cd backend
   ```

2. **Create environment file:**
   ```bash
   cp .env.template .env
   ```

3. **Configure `.env` file** with your:
   - Database URLs
   - API keys
   - Redis credentials
   - Firebase credentials

4. **Install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

5. **Set up ngrok** for local development:
   ```bash
   ngrok http --domain=your-domain.ngrok-free.app 8000
   ```

6. **Start the backend:**
   ```bash
   uvicorn main:app --reload --env-file .env
   ```

7. **Update app configuration** to point to your backend:
   - Edit `app/.dev.env` and set `API_BASE_URL` to your ngrok URL

See [backend/README.md](backend/README.md) for detailed instructions.

## Code Structure

### Key Files

- **Device Connection**: [`app/lib/services/devices/limitless_connection.dart`](app/lib/services/devices/limitless_connection.dart)
  - Full BLE protocol implementation (~1500 lines)
  - Handles connection, audio streaming, offline sync, button events

- **Device Detection**: [`app/lib/backend/schema/bt_device/bt_device.dart`](app/lib/backend/schema/bt_device/bt_device.dart)
  - Detects Limitless devices during Bluetooth scan
  - Maps device type to connection handler

- **Sync UI**: [`app/lib/pages/capture/widgets/limitless_sync_widget.dart`](app/lib/pages/capture/widgets/limitless_sync_widget.dart)
  - UI for syncing offline recordings
  - Shows progress and sync status

- **Device Discovery**: [`app/lib/pages/onboarding/find_device/found_devices.dart`](app/lib/pages/onboarding/find_device/found_devices.dart)
  - UI for finding and pairing devices

## Troubleshooting

### Device Not Found

- Ensure Bluetooth is enabled on your phone
- Make sure the pendant is powered on and in pairing mode
- Check that the device name contains "limitless" or "pendant"
- Try restarting the app

### Connection Fails

- Ensure the pendant is not connected to another device
- Try forgetting the device in your phone's Bluetooth settings
- Restart both the app and the pendant

### Audio Not Streaming

- Check that the app has microphone permissions
- Verify the connection is established (check device status in app)
- Ensure backend is accessible (if self-hosting)

### Offline Sync Not Working

- Make sure you have stored recordings on the pendant
- Check the sync widget appears when connected
- Try manually triggering sync from the sync widget

## Customization Options

### Adding Short Press Handling

Edit [`app/lib/services/devices/limitless_connection.dart`](app/lib/services/devices/limitless_connection.dart):

```dart
// In _tryParseButtonStatus method, around line 1095
if (buttonEvent == _buttonShortPress) {
  // Add your custom action here
  // e.g., trigger a specific app function
  return;
}
```

### Improving Flash Page Acknowledgment

The current implementation acknowledges processed data. You can improve this by:
- Adding retry logic for failed acknowledgments
- Batching acknowledgments for better performance
- Adding progress callbacks

### Device Status Display

Add UI to show:
- Storage capacity (free/total flash pages)
- Current session info
- Device firmware version

## Next Steps

1. ✅ Build and run the OMI app
2. ✅ Pair your Limitless pendant
3. ✅ Test real-time transcription
4. ✅ Test offline recording sync
5. ⏭️ Explore code customization options
6. ⏭️ Set up self-hosted backend (optional)

## Support

- **Documentation**: [https://docs.omi.me/](https://docs.omi.me/)
- **Discord**: [http://discord.omi.me](http://discord.omi.me)
- **GitHub Issues**: [https://github.com/BasedHardware/Omi/issues](https://github.com/BasedHardware/Omi/issues)

## Technical Notes

### Why No Firmware Changes?

The Limitless pendant uses a standard Bluetooth Low Energy (BLE) protocol. OMI's app implements a client for this protocol, so it can communicate with the pendant without modifying the device firmware. This is similar to how multiple apps can connect to the same Bluetooth speaker.

### Protocol Compatibility

The OMI implementation is based on reverse-engineering the Limitless protocol. It handles:
- Protobuf-style message encoding/decoding
- BLE packet fragmentation
- Opus frame extraction and validation
- Flash page parsing for offline recordings

### Future Enhancements

Potential improvements you could contribute:
- Better error handling and recovery
- Support for additional Limitless device features
- Performance optimizations for large offline syncs
- Enhanced button mapping options

