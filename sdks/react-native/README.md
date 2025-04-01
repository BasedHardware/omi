# React Native SDK Documentation

## Installation

To install the React Native SDK, follow the instructions provided in the [official documentation](https://docs.omi.me/docs/developer/sdk/ReactNative).

## Usage

### Streaming Audio

```javascript
import { OmiSDK } from 'omi-sdk';

// Initialize SDK
const omiSDK = new OmiSDK();

// Start streaming audio
omiSDK.startStreamingAudio('https://example.com/stream');
```

### Battery Monitoring

```javascript
// Get battery level
const batteryLevel = omiSDK.getBatteryLevel();
console.log(`Battery Level: ${batteryLevel}%`);
```

## API Reference

For a complete list of API methods and their usage, refer to the [API reference](https://docs.omi.me/docs/developer/sdk/ReactNative/api-reference).

## Troubleshooting

If you encounter any issues, please check the [troubleshooting guide](https://docs.omi.me/docs/developer/sdk/ReactNative/troubleshooting) or contact support.
