# Omi Watch App - watchOS 26 Enhanced

## Overview

The Omi Watch App is a native watchOS application that enables audio recording directly from Apple Watch. This version has been significantly enhanced for watchOS 26, featuring Apple's Liquid Glass design system, improved performance, and modern watchOS capabilities.

## watchOS 26 Features

### 1. Liquid Glass Design System

The app now implements Apple's Liquid Glass design language, introduced in watchOS 26:

#### Visual Enhancements
- **Translucent Materials**: All UI elements use glass-like materials that reflect and refract light
- **Depth-Aware Surfaces**: Button and container surfaces respond to user interaction with depth effects
- **Dynamic Gradients**: Linear gradients create visual depth and hierarchy
- **Adaptive Luminance**: UI automatically adjusts for Always-On Display mode

#### Implementation Details
```swift
// Liquid Glass button with gradient fill
Circle()
    .fill(
        LinearGradient(
            gradient: Gradient(colors: [
                Color.white,
                Color.white.opacity(0.9)
            ]),
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    )
```

### 2. Enhanced Animations

- **Spring Physics**: Natural spring animations with configurable response and damping
- **Ripple Effects**: Enhanced pulsating ripples during recording with gradient strokes
- **State Transitions**: Smooth transitions between recording states

```swift
withAnimation(.spring(response: 0.3, dampingFraction: 0.6)) {
    isPressed = true
    glassIntensity = 1.0
}
```

### 3. Haptic Feedback

Enhanced tactile feedback for watchOS 26:

```swift
WKInterfaceDevice.current().play(.click)
```

### 4. Smart Stack Widget

New widget integration for Quick Actions and Smart Stack:

- **Circular Widget**: Compact recording status display
- **Rectangular Widget**: Detailed status with battery level
- **Corner Widget**: Minimal corner display for watch faces

**Widget Families Supported:**
- `.accessoryCircular`
- `.accessoryRectangular`
- `.accessoryCorner`

### 5. Enhanced Logging

Unified Logging system for better debugging:

```swift
import os.log
private let logger = Logger(subsystem: "com.omi.watchapp", category: "AudioRecorder")
logger.info("Recording started successfully")
```

## Architecture

### Core Components

#### 1. WatchRecorderView (ContentView.swift)
The main user interface with Liquid Glass enhancements:
- Responsive button with spring animations
- Recording status indicator
- Audio visualization (ripple effects)
- Adaptive to Always-On Display mode

#### 2. WatchAudioRecorderViewModel
Enhanced audio recording engine:
- **Modern Async/Await**: Updated for Swift concurrency
- **Audio Level Tracking**: Real-time audio visualization
- **Duration Tracking**: Live recording duration display
- **Error Handling**: Comprehensive error reporting
- **Message Reliability**: Automatic fallback between `sendMessage` and `transferUserInfo`

**New Published Properties:**
```swift
@Published var recordingDuration: TimeInterval = 0
@Published var audioLevel: Float = 0.0
@Published var errorMessage: String?
```

#### 3. BatteryManager
Enhanced battery monitoring:
- **Smart Updates**: Only sends when battery level changes significantly
- **Timestamp Tracking**: All updates include timestamps
- **Screen Bounds**: Reports watch screen dimensions
- **Deduplication**: Avoids redundant network calls

**New Features:**
```swift
func getBatteryInfo() -> [String: Any]
func sendBatteryLevel(force: Bool = false)
```

#### 4. OmiWidget (New)
Smart Stack widget for watchOS 26:
- TimelineProvider for scheduled updates
- Three widget families supported
- Liquid Glass styling throughout
- Battery and recording status display

## Technical Specifications

### Deployment Target
- **Minimum Version**: watchOS 26.0
- **Development SDK**: Xcode 26+
- **Swift Version**: 5.0+

### Audio Specifications
- **Sample Rate**: 16kHz (resampled from hardware rate)
- **Format**: PCM16 (16-bit Linear PCM)
- **Channels**: Mono (1 channel)
- **Buffer Duration**: 1.5 seconds
- **Audio Session Category**: `.playAndRecord` with `.mixWithOthers`

### Communication Protocol
- **Primary**: `WCSession.sendMessage` for real-time delivery
- **Fallback**: `WCSession.transferUserInfo` for reliability
- **Automatic Fallback**: Triggers on send failure or when not reachable

### Battery Monitoring
- **Update Interval**: 3 minutes
- **Deduplication**: Updates only sent when level changes >1%
- **Monitoring**: Automatic via WKInterfaceDevice

## New Features in This Release

### 1. Liquid Glass UI
✅ Complete UI redesign with Liquid Glass materials
✅ Enhanced gradients and depth effects
✅ Always-On Display optimization
✅ Improved visual hierarchy

### 2. Modern Swift APIs
✅ Swift Concurrency (async/await)
✅ MainActor isolation for thread safety
✅ Unified Logging framework
✅ Enhanced error handling

### 3. Smart Widget
✅ Three widget families
✅ Smart Stack integration
✅ Timeline-based updates
✅ Battery and recording status

### 4. Enhanced Audio
✅ Real-time audio level tracking
✅ Recording duration display
✅ Improved buffering system
✅ Better error recovery

### 5. Improved Reliability
✅ Message delivery fallback
✅ Battery update deduplication
✅ Comprehensive logging
✅ State management improvements

## Testing

### Test Coverage

The app includes comprehensive test suites:

#### Unit Tests
- `WatchAudioRecorderViewModelTests.swift`: ViewModel logic and state management
- `BatteryManagerTests.swift`: Battery monitoring and reporting
- `ContentViewTests.swift`: UI components and interactions

#### Integration Tests
- `IntegrationTests.swift`: End-to-end workflows
  - Complete recording workflows
  - Battery-recording integration
  - WatchConnectivity messaging
  - Concurrency and stress tests

### Running Tests

```bash
# Run all tests
xcodebuild test -scheme omiWatchApp -destination 'platform=watchOS Simulator,name=Apple Watch Series 9 (45mm)'

# Run specific test suite
xcodebuild test -scheme omiWatchApp -only-testing:omiWatchAppTests/WatchAudioRecorderViewModelTests
```

## API Reference

### WatchAudioRecorderViewModel

```swift
@MainActor
class WatchAudioRecorderViewModel: ObservableObject {
    // Published Properties
    @Published var isRecording: Bool
    @Published var recordingDuration: TimeInterval
    @Published var audioLevel: Float
    @Published var errorMessage: String?

    // Public Methods
    func startRecording()
    func stopRecording()
    func requestMicrophonePermissionOnly()
}
```

### BatteryManager

```swift
class BatteryManager {
    static let shared: BatteryManager

    func startBatteryMonitoring()
    func stopBatteryMonitoring()
    func sendBatteryLevel(force: Bool = false)
    func sendWatchInfo()
    func getBatteryInfo() -> [String: Any]
}
```

### OmiWidget

```swift
struct OmiWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "OmiWidget", provider: OmiWidgetProvider()) { entry in
            OmiWidgetView(entry: entry)
        }
        .supportedFamilies([
            .accessoryCircular,
            .accessoryRectangular,
            .accessoryCorner
        ])
    }
}
```

## Communication Protocol

### Message Types

#### From Watch to Phone

1. **startRecording**
```json
{
    "method": "startRecording"
}
```

2. **stopRecording**
```json
{
    "method": "stopRecording"
}
```

3. **sendAudioChunk**
```json
{
    "method": "sendAudioChunk",
    "audioChunk": Data,
    "chunkIndex": Int,
    "isLast": Bool,
    "sampleRate": 16000.0
}
```

4. **batteryUpdate**
```json
{
    "method": "batteryUpdate",
    "batteryLevel": Float,
    "batteryState": Int,
    "timestamp": Double
}
```

5. **watchInfoUpdate**
```json
{
    "method": "watchInfoUpdate",
    "name": String,
    "model": String,
    "systemVersion": String,
    "localizedModel": String,
    "screenBounds": { "width": Double, "height": Double },
    "timestamp": Double
}
```

#### From Phone to Watch

1. **startRecording**
2. **stopRecording**
3. **requestMicrophonePermission**
4. **requestBattery**
5. **requestWatchInfo**

## Performance Optimizations

### Memory Management
- Efficient audio buffer reuse
- Automatic cleanup on recording stop
- Weak references to prevent retain cycles

### Network Efficiency
- 1.5-second audio chunks (optimal for watchOS)
- Battery update deduplication
- Automatic fallback messaging

### Power Efficiency
- 3-minute battery update interval
- Conditional updates only when changed
- Efficient audio resampling

## Backwards Compatibility

While optimized for watchOS 26, the app maintains core functionality on earlier versions:
- watchOS 11+: Full audio recording support
- watchOS 10+: Basic recording with limited Liquid Glass effects
- Earlier versions: Not supported (deployment target is watchOS 26)

## Known Issues and Limitations

1. **Permissions**: Microphone permissions must be granted both on iPhone and Watch
2. **Connectivity**: Requires paired iPhone for full functionality
3. **Battery Impact**: Continuous recording affects battery life
4. **Background Limits**: watchOS restricts background audio processing

## Future Enhancements

Potential features for future releases:
- [ ] RelevanceKit integration for contextual widget updates
- [ ] Live Activities for active recording sessions
- [ ] On-device audio processing with Neural Engine
- [ ] Complications for watch faces
- [ ] Voice shortcuts integration
- [ ] Health app integration for audio health metrics

## Troubleshooting

### Recording Not Starting
1. Check microphone permissions on both iPhone and Watch
2. Ensure Watch and iPhone are connected
3. Verify WatchConnectivity session is active
4. Check console logs for error messages

### Audio Quality Issues
1. Verify hardware sample rate detection
2. Check audio converter configuration
3. Ensure proper audio session setup
3. Review buffer size and chunk duration

### Battery Updates Not Received
1. Verify WCSession is reachable
2. Check transferUserInfo fallback
3. Review battery monitoring state
4. Check connection between devices

## Development

### Build Requirements
- Xcode 26+
- iOS 26 SDK
- watchOS 26 SDK
- macOS Tahoe or later

### Build Configuration
```bash
# Debug build
xcodebuild -scheme omiWatchApp -configuration Debug

# Release build
xcodebuild -scheme omiWatchApp -configuration Release

# Archive for distribution
xcodebuild archive -scheme omiWatchApp -archivePath ./build/omiWatchApp.xcarchive
```

## Credits

- **watchOS 26 Features**: Based on Apple's WWDC 2025 sessions
- **Liquid Glass Design**: Implementing Apple's design guidelines
- **Audio Processing**: AVFoundation and CoreAudio
- **Connectivity**: WatchConnectivity framework

## License

Part of the Omi project. See main project LICENSE for details.

## Support

For issues, questions, or contributions:
- **Project**: https://github.com/BasedHardware/omi
- **Issues**: https://github.com/BasedHardware/omi/issues
- **Documentation**: https://github.com/BasedHardware/omi/wiki

---

**Last Updated**: October 2025
**watchOS Version**: 26.0
**App Version**: 2.0.0
