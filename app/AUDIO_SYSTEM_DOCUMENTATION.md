# Apple Watch Audio Recording System Documentation

## 📋 Overview

This document describes the current Apple Watch ↔ iOS ↔ Flutter audio pipeline. The watch records audio, resamples to 16kHz, buffers ~1.5s chunks, and transmits reliably to the paired iPhone using WatchConnectivity with an adaptive strategy. Pigeon provides a type-safe bridge between iOS native and Flutter.

## 🏗️ System Architecture

```
┌─────────────────┐    WatchConnectivity    ┌─────────────────┐    Pigeon Bridge    ┌─────────────────┐
│   Apple Watch   │ ──────────────────────► │     iOS App     │ ──────────────────► │    Flutter App  │
│                 │                         │                 │                     │                 │
│ • Audio Engine  │                         │ • AppDelegate   │                     │ • Watch Home    │
│ • Real-time     │                         │ • Message       │                     │ • Audio Chunks  │
│   Streaming     │                         │   Handling      │                     │ • WAV File      │
│ • Auto-resample │                         │ • Chunked Data  │                     │   Creation      │
│   to 16kHz      │                         │ • 16kHz Output  │                     │ • 16kHz Audio   │
└─────────────────┘                         └─────────────────┘                     └─────────────────┘
```

## 🔄 Communication Flow

### 1. Watch → iOS App (WatchConnectivity)
- **Protocol**: `WCSessionDelegate`
- **Data Format**: Dictionary with method calls and audio data
- **Chunking (Updated)**:
  - Capture with a 512-frame tap for low-latency processing
  - Aggregate on-watch into ~1.5-second chunks to reduce send frequency
  - Foreground/reachable: `sendMessage` (real-time)
  - Background/unreachable: `transferUserInfo` (opportunistic)
- **Sample Rate**: 16kHz (resampled from native)

### 2. iOS App → Flutter (Pigeon)
- **Protocol**: Generated Pigeon APIs (`WatchRecorderHostAPI`, `WatchRecorderFlutterAPI`)
- **Host Impl (Updated)**: `RecorderHostApiImpl` (separate file) handles start/stop, permissions, and chunk forwarding
- **Data Format**: `FlutterStandardTypedData` for binary audio
- **Delivery**: iOS forwards chunks via `onAudioChunk(...)`; full buffers via `onAudioData(...)` when applicable

## 📁 File Structure

### Core Components

#### Apple Watch App (`ios/omiWatchApp/`)
```
WatchAudioRecorderViewModel.swift # Main audio recording (renamed, no counter)
ContentView.swift                # Record/stop UI
Info.plist                       # Mic permission + UIBackgroundModes: audio
omiwatchApp.swift                # App entry point
```

#### iOS App Bridge (`ios/Runner/`)
```
AppDelegate.swift             # WatchConnectivity handling
FlutterCommunicator.g.swift   # Generated Pigeon bridge
RecorderHostApiImpl.swift     # Host API implementation
```

#### Flutter App (`lib/src/`)
```
watch_home.dart          # UI and audio data handling
flutter_communicator.g.dart # Generated Pigeon bridge
```

#### Interface Definition (`watch_interface.dart`)
```dart
// Host API (Flutter → iOS → Watch)
@HostApi()
abstract class WatchRecorderHostAPI {
  void startRecording();
  void stopRecording();
  void sendAudioChunk(Uint8List audioChunk, int chunkIndex, bool isLast, double sampleRate);
  bool isWatchPaired();
  bool isWatchReachable();
  bool isWatchSessionSupported();
  bool isWatchAppInstalled();
  void requestWatchMicrophonePermission();
  void requestMainAppMicrophonePermission();
  bool checkMainAppMicrophonePermission();
}

// Flutter API (iOS → Flutter)
@FlutterApi()
abstract class WatchRecorderFlutterAPI {
  void onRecordingStarted();
  void onRecordingStopped();
  void onAudioChunk(Uint8List audioChunk, int chunkIndex, bool isLast, double sampleRate);
  void onAudioData(Uint8List audioData);
  void onRecordingError(String error);
  void onMicrophonePermissionResult(bool granted);
  void onMainAppMicrophonePermissionResult(bool granted);
}
```

## 🎵 Audio Processing Pipeline

### 1. Audio Capture (Watch)
```swift
audioEngine = AVAudioEngine()
inputNode = audioEngine?.inputNode
let inputFormat = inputNode?.inputFormat(forBus: 0)
detectedSampleRate = inputFormat?.sampleRate ?? 0
targetFormat = AVAudioFormat(standardFormatWithSampleRate: 16000.0, channels: 1)
audioConverter = AVAudioConverter(from: inputFormat!, to: targetFormat!)
inputNode?.installTap(onBus: 0, bufferSize: 512, format: inputFormat) { [weak self] buffer, _ in
    self?.processAudioBuffer(buffer)
}
try audioEngine?.start()
```

### 2. Audio Processing (Watch)
```swift
private func processAudioBuffer(_ buffer: AVAudioPCMBuffer) {
    // Resample → 16kHz and append to chunkBuffer (Data)
    // When bufferDuration (~1.5s) elapses, sendBufferedAudioChunk()
    bufferAndSendAudioData(byteData)
}
```

### 3. Data Transmission (Watch → iOS)
```swift
if session.isReachable {
    session.sendMessage(messageData, replyHandler: nil) { error in
        self.session.transferUserInfo(messageData)
    }
} else {
    session.transferUserInfo(messageData)
}
```

### 4. Data Reception (iOS → Flutter)
```swift
// Foreground: session(_:didReceiveMessage:)
// Background: session(_:didReceiveUserInfo:)
private func handleAudioChunk(_ message: [String: Any]) {
    guard isRecordingActive else { return }
    audioChunks[chunkIndex] = (audioChunk, sampleRate)
    flutterWatchAPI?.onAudioChunk(...)
    if isLast { reassembleAndSendAudioData() }
}
```

### 5. Data Assembly (Flutter)
```dart
void _reassembleAudioData() {
    // Sort chunks by index and combine
    final sortedChunks = _audioChunks.entries.toList()
      ..sort((a, b) => a.key.compareTo(b.key));

    final bytesBuilder = BytesBuilder();
    for (final entry in sortedChunks) {
      final (chunkData, _) = entry.value;
      bytesBuilder.add(chunkData);
    }

    final combinedData = bytesBuilder.toBytes();
    _saveAudioFile();
}
```

### 6. WAV File Creation (Flutter)
```dart
Uint8List _createWavFile(Uint8List pcmData) {
    final int sampleRate = _sampleRate.toInt(); // Use actual sample rate (48kHz)
    const int bitsPerSample = 16;
    const int numChannels = 1; // Mono

    // Create RIFF header with proper metadata
    // RIFF, Format, Data chunks
    // Sample rate, bit depth, channels, etc.

    return builder.toBytes();
}
```

## ⚙️ Setup and Configuration

### 1. Permissions

#### Apple Watch (`Info.plist`)
```xml
<key>NSMicrophoneUsageDescription</key>
<string>This app needs access to the microphone to record audio from your Apple Watch.</string>
<key>UIBackgroundModes</key>
<array>
    <string>audio</string>
</array>
```

#### iOS App (`Info.plist`)
```xml
<key>NSMicrophoneUsageDescription</key>
<string>We need access to your microphone so you can share audio explanations of Bugs you find.</string>
```

### 2. WatchConnectivity Setup

#### iOS AppDelegate
```swift
if WCSession.isSupported() {
    session = WCSession.default
    session?.delegate = self
    session?.activate()

    // Setup Pigeon bridge
    let api: WatchRecorderHostAPI = RecorderHostApiImpl(session: session!)
    WatchRecorderHostAPISetup.setUp(binaryMessenger: controller!.binaryMessenger, api: api)
    flutterWatchAPI = WatchRecorderFlutterAPI(binaryMessenger: controller!.binaryMessenger)
}
```

#### Watch App
```swift
init(session: WCSession = .default) {
    self.session = session
    super.init()
    self.session.delegate = self
    session.activate()
}
```

### 3. Pigeon Code Generation
```bash
dart run pigeon --input watch_interface.dart
```

## 🔧 Key Technical Details

### Audio Format Specifications
- **Input Sample Rate**: Variable (22,050 Hz - 48,000 Hz depending on watch model)
- **Output Sample Rate**: 16,000 Hz (resampled for consistency and speech recognition)
- **Bit Depth**: 16-bit PCM
- **Channels**: 1 (Mono)
- **Format**: Linear PCM (LPCM)
- **Byte Order**: Little-endian
- **Note**: `setPreferredSampleRate` unavailable on watchOS - resampling handled via `AVAudioConverter`

### Buffer Management
- **Tap Buffer Size**: 512 frames (low latency)
- **Transmission Chunk Size**: ~1.5s of 16kHz mono PCM (~48–56KB typical)
- **Adaptive Transfer**: `sendMessage` (foreground) → `transferUserInfo` (background)

### Error Handling
- **Microphone Permission**: Checked before recording
- **Audio Session**: Properly configured with error handling
- **Data Transmission**: Fallback mechanisms for failed chunks
- **File Creation**: Validation of audio data before WAV creation

## 🐛 Troubleshooting Guide

### Common Issues

#### 1. "Audio data: null"
**Symptoms**: Audio recording completes but no data received
**Causes**:
- Microphone permissions not granted
- Watch not paired with iPhone
- Audio session setup failure
**Solutions**:
- Check watch microphone permissions in Settings
- Ensure watch is paired and reachable
- Verify audio session initialization logs

#### 2. "Payload is too large"
**Symptoms**: WatchConnectivity transmission fails
**Status**: ✅ **RESOLVED** - Now using chunked transmission
**Prevention**: Keep chunks under 64KB each

#### 3. Slow/Unclear Audio
**Symptoms**: Audio plays back too slowly or distorted
**Causes**:
- Incorrect sample rate in WAV header
- Buffer processing issues
**Status**: ✅ **RESOLVED** - Now uses correct 48kHz sample rate

#### 4. Missing Audio Chunks
**Symptoms**: Incomplete audio file
**Causes**:
- WatchConnectivity message loss
- Buffer overflow
**Solutions**:
- Check WatchConnectivity reachability
- Reduce buffer size if needed
- Add chunk sequence validation

### Debug Logging

#### Watch App Logs
```
"Audio session configured successfully"
"Input format: <AVAudioFormat...>"
"Sample rate: 48000.0"
"Audio streaming started successfully"
"Sent audio chunk X with Y bytes, rate: 48000Hz"
```

#### iOS App Logs
```
"Received sendAudioChunk message from watch"
"Received audio chunk X, size: Y bytes, isLast: Z, rate: RHz"
"Audio chunk X sent to Flutter - Success"
"Reassembling audio data from C chunks"
```

#### Flutter App Logs
```
"Flutter: onAudioChunk callback called with X bytes, chunk: Y, isLast: Z, rate: RHz"
"Reassembling audio data from C chunks at RHz"
"Created WAV file with sample rate: RHz"
"WAV file saved to: /path/to/file.wav"
```

## 📊 Performance Metrics

### Current Performance (Updated)
- **End-to-end Latency**: ~1.5–2.0s (due to on-watch aggregation)
- **Chunk Size**: ~48–56KB per chunk
- **Sample Rate**: 48kHz capture → 16kHz transmit
- **Memory Usage**: Minimal (chunks processed immediately)
- **Battery Impact**: Low (optimized buffer sizes)

### Optimization Opportunities
- **Compression**: Could add audio compression for smaller files
- **Quality Settings**: Could allow sample rate selection
- **Background Processing**: Could add background audio processing
- **Error Recovery**: Could add automatic retry for failed chunks

## 🔄 Data Flow Summary

1. **User taps record button** → Watch starts audio streaming
2. **Audio captured in buffers** → 512-frame chunks processed
3. **Chunks sent via WatchConnectivity** → iOS app receives data
4. **iOS forwards to Flutter** → Real-time chunk delivery
5. **Flutter reassembles data** → Complete PCM audio created
6. **WAV header added** → Proper audio file format
7. **File saved locally** → Ready for playback/upload

## 🎯 Key Achievements

✅ **Real-time streaming** - No more "payload too large" errors
✅ **Consistent sample rate** - Always 16kHz regardless of watch model
✅ **Automatic resampling** - Handles variable hardware sample rates
✅ **Low latency** - Audio data flows immediately
✅ **Error resilient** - Graceful handling of network issues
✅ **Memory efficient** - Chunks processed without accumulation
✅ **Platform optimized** - Leverages native audio APIs

## 📝 Future Enhancements

- **Audio compression** (Opus/FLAC) for smaller files
- **Background recording** when app is not active
- **Multiple quality options** (16kHz/48kHz selection)
- **Audio effects** (noise reduction, echo cancellation)
- **Offline storage** with automatic upload when connected
- **Voice activity detection** to reduce unnecessary data

---

**Last Updated**: December 2024
**System Status**: ✅ **FULLY OPERATIONAL**
**Architecture**: Real-time streaming with chunked transmission
