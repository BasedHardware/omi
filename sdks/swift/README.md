# Swift SDK Documentation

## Installation

To install the Swift SDK, follow the instructions provided in the [official documentation](https://docs.omi.me/docs/developer/sdk/swift).

## Usage

### Streaming Audio

```swift
import OmiSDK

// Initialize SDK
let omiSDK = OmiSDK()

// Start streaming audio
omiSDK.startStreamingAudio(url: "https://example.com/stream")
```

### Battery Monitoring

```swift
// Get battery level
let batteryLevel = omiSDK.getBatteryLevel()
print("Battery Level: \(batteryLevel)%")
```

## API Reference

For a complete list of API methods and their usage, refer to the [API reference](https://docs.omi.me/docs/developer/sdk/swift/api-reference).

## Troubleshooting

If you encounter any issues, please check the [troubleshooting guide](https://docs.omi.me/docs/developer/sdk/swift/troubleshooting) or contact support.
