<!--
⚠️ This file is auto-generated from docs/docs/docs/developer/sdk/ReactNative.mdx. Do not edit manually.
-->


# Omi SDK for React Native

A React Native SDK for connecting to and interacting with Omi devices via Bluetooth Low Energy (BLE).

## Features

- Scan for nearby Omi devices
- Connect to Omi devices
- Get device audio codec information
- Stream audio data from the device
- Monitor battery levels
- Handle connection state changes
- Real-time audio transcription using Deepgram

## Development Setup

### Prerequisites

- Node.js and npm installed
- Xcode (for iOS development)
- Android Studio (for Android development)
- CocoaPods (for iOS development)

### Installation

1. Clone the repository and navigate to the react-native directory:
```bash
git clone https://github.com/BasedHardware/omi.git

cd sdks/react-native
```

2. Install dependencies:
```bash
npm install
```

3. Navigate to the example app directory and install its dependencies:
```bash
cd example
npm install
```

4. For iOS development, install CocoaPods dependencies:
```bash
cd ios
pod install
```

Note: The `pod install` step is crucial and must not be skipped for iOS development. Without it, the app will fail to build with native module errors.

### Running the Example App

#### iOS
1. Make sure you've completed all installation steps above
2. Open the example app's workspace in Xcode:
```bash
cd example/ios
open OmiSDKExample.xcworkspace  # Do NOT open the .xcodeproj file
```
3. Select your target device (Note: Bluetooth functionality is not available in simulators)
4. Build and run the project

#### Android
1. Connect your Android device via USB
2. Enable USB debugging on your device
3. Run the app:
```bash
cd example
npm run android
```

## Installation in Your Project

```bash
npm install @omiai/omi-react-native
# or
yarn add @omiai/omi-react-native
```

### Dependencies

This SDK relies on [react-native-ble-plx](https://github.com/Polidea/react-native-ble-plx) for BLE communication.

```bash
npm install react-native-ble-plx
# or
yarn add react-native-ble-plx
```

After installing the dependencies, for iOS projects you MUST run:
```bash
cd ios
pod install
```

### Platform-Specific Setup

For iOS, add the following to your `Info.plist`:

```xml
<key>NSBluetoothAlwaysUsageDescription</key>
<string>This app uses Bluetooth to connect to Omi devices</string>
<key>NSBluetoothPeripheralUsageDescription</key>
<string>This app uses Bluetooth to connect to Omi devices</string>
```

For Android, add the following permissions to your `AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.BLUETOOTH"/>
<uses-permission android:name="android.permission.BLUETOOTH_ADMIN"/>
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
<!-- For Android 12+ -->
<uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
```

## Usage

### Basic Example

```javascript
import { OmiConnection, DeviceConnectionState, BleAudioCodec } from '@omiai/omi-react-native';

// Create an instance of OmiConnection
const omiConnection = new OmiConnection();

// Scan for devices
const stopScan = omiConnection.scanForDevices((device) => {
  console.log('Found device:', device.name, device.id);
}, 10000); // Scan for 10 seconds

// Connect to a device
async function connectToDevice(deviceId) {
  const success = await omiConnection.connect(deviceId, (id, state) => {
    console.log(`Device ${id} connection state changed to: ${state}`);
  });
  
  if (success) {
    console.log('Connected successfully!');
    
    // Get the audio codec
    const codec = await omiConnection.getAudioCodec();
    console.log('Device audio codec:', codec);
    
    // Start listening for audio data
    const subscription = await omiConnection.startAudioBytesListener((bytes) => {
      console.log('Received audio bytes:', bytes.length);
      // Process audio bytes here
    });
    
    // Get battery level
    const batteryLevel = await omiConnection.getBatteryLevel();
    console.log('Battery level:', batteryLevel);
    
    // Later, stop listening for audio
    await omiConnection.stopAudioBytesListener(subscription);
    
    // Disconnect when done
    await omiConnection.disconnect();
  }
}
```

## API Reference

### OmiConnection

The main class for interacting with Omi devices.

#### Methods

##### `scanForDevices(onDeviceFound, timeoutMs = 10000)`

Scans for nearby Omi devices.

- `onDeviceFound`: Callback function that receives an OmiDevice object when a device is found
- `timeoutMs`: Scan timeout in milliseconds (default: 10000)
- Returns: A function to stop scanning

##### `connect(deviceId, onConnectionStateChanged)`

Connects to an Omi device.

- `deviceId`: The ID of the device to connect to
- `onConnectionStateChanged`: Optional callback for connection state changes
- Returns: Promise that resolves to a boolean indicating success

##### `disconnect()`

Disconnects from the currently connected device.

- Returns: Promise that resolves when disconnected

##### `isConnected()`

Checks if connected to a device.

- Returns: Boolean indicating if connected

##### `getAudioCodec()`

Gets the audio codec used by the device.

- Returns: Promise that resolves with the audio codec (BleAudioCodec enum)

##### `startAudioBytesListener(onAudioBytesReceived)`

Starts listening for audio bytes from the device.

- `onAudioBytesReceived`: Callback function that receives audio bytes as a number array
- Returns: Promise that resolves with a subscription that can be used to stop listening

##### `stopAudioBytesListener(subscription)`

Stops listening for audio bytes.

- `subscription`: The subscription returned by startAudioBytesListener
- Returns: Promise that resolves when stopped

##### `getBatteryLevel()`

Gets the current battery level from the device.

- Returns: Promise that resolves with the battery level percentage (0-100)

### Types

#### OmiDevice

```typescript
interface OmiDevice {
  id: string;
  name: string;
  rssi: number;
}
```

#### DeviceConnectionState

```typescript
enum DeviceConnectionState {
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected'
}
```

#### BleAudioCodec

```typescript
enum BleAudioCodec {
  PCM16 = 'pcm16',
  PCM8 = 'pcm8',
  OPUS = 'opus',
  UNKNOWN = 'unknown'
}
```

## Troubleshooting

### Common Issues

1. **Build fails with native module errors on iOS**
   - Ensure you've run `pod install` in the ios directory
   - Try cleaning the build folder in Xcode (Product → Clean Build Folder)
   - Make sure you're opening the `.xcworkspace` file, not the `.xcodeproj` file

2. **Device not found during scanning**
   - Ensure Bluetooth is enabled on your device
   - Check that you have the necessary permissions
   - Make sure the Omi device is powered on and in range
   - Note: Bluetooth scanning does not work in iOS simulators, use a physical device

3. **Connection fails**
   - Try restarting the Omi device
   - Ensure the device is not connected to another application
   - Check battery level of the Omi device

4. **Audio data not received**
   - Verify that the device supports the audio service
   - Check that you're properly handling the audio bytes in your callback

5. **Transcription not working**
   - Ensure you have a valid Deepgram API key
   - Check that the audio listener is started before enabling transcription
   - Verify your internet connection is stable

6. **Keyboard overlaps input fields**
   - The example app includes padding at the bottom of the ScrollView to ensure input fields remain visible when the keyboard is open

## License

MIT
