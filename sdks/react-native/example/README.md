# Omi SDK Example App

This is a comprehensive example application demonstrating how to use the Omi SDK for React Native to connect to and interact with Omi devices.

## Features

- Scan for nearby Omi devices
- Connect to and disconnect from devices
- Get audio codec information
- Monitor battery levels
- Stream audio data from the device
- Real-time audio transcription using Deepgram API

## Prerequisites

- React Native development environment
- An Omi device for testing
- (Optional) Deepgram API key for transcription features

## Installation

1. Clone the repository
2. Install dependencies:

```bash
cd sdks/react-native/example
npm install
# or
yarn install
```

3. For iOS, install pods:

```bash
cd ios
pod install
cd ..
```

## Running the Example

### iOS

```bash
npx react-native run-ios
```

### Android

```bash
npx react-native run-android
```

## Usage Guide

### Bluetooth Permissions

The app will automatically request Bluetooth permissions when needed. If permissions are denied, you'll see a banner with instructions to enable them.

### Scanning for Devices

1. Tap "Scan for Devices" to begin searching for nearby Omi devices
2. The scan will automatically stop after 30 seconds, or you can tap "Stop Scan" to end it manually
3. Found devices will appear in the list with their name and signal strength (RSSI)

### Connecting to a Device

1. Tap "Connect" next to the device you want to connect to
2. Once connected, additional device functions will become available
3. To disconnect, tap "Disconnect"

### Device Functions

Once connected, you can:

- **Get Audio Codec**: Retrieves the audio codec used by the device
- **Get Battery Level**: Shows the current battery percentage
- **Start/Stop Audio Listener**: Begins/ends streaming audio data from the device

### Transcription (Optional)

The app includes integration with Deepgram for real-time audio transcription:

1. Enable the "Enable Transcription" checkbox
2. Enter your Deepgram API key
3. Start the audio listener
4. Tap "Start Transcription" to begin converting audio to text
5. Transcription results will appear at the bottom of the screen

## Troubleshooting

### Common Issues

1. **Device not found during scanning**
   - Ensure Bluetooth is enabled on your device
   - Check that you have granted the necessary permissions
   - Make sure the Omi device is powered on and in range

2. **Connection fails**
   - Try restarting the Omi device
   - Ensure the device is not connected to another application
   - Check the battery level of the Omi device

3. **Audio data not received**
   - Verify that the device supports the audio service
   - Check that the device is properly connected

4. **Transcription not working**
   - Verify your Deepgram API key is correct
   - Ensure you have an active internet connection
   - Check that audio is being received from the device

## Code Structure

The example app demonstrates:

- Proper lifecycle management of BLE connections
- Handling permissions on both iOS and Android
- Efficient audio data processing
- Integration with third-party services (Deepgram)
- Responsive UI for different device states

## License

MIT
