# Fix audio clicking and time slippage issues (#2165)

## Problem Description

This PR addresses issue #2165 which reported persistent clicking noise in audio recordings and audio clip duration inconsistencies on multiple Omi Dev Kits. The issue was affecting transcription quality and audio processing reliability.

### Symptoms
- Persistent clicking noise in audio recordings
- Audio clip durations inconsistent (e.g., set for 10s, but files were 25–50s long)
- Opus frame decoding errors in backend logs
- Issues occurred on various smartphones with firmware v2.02

## Root Cause Analysis

After investigating the codebase, I identified three main causes:

1. **Firmware Ring Buffer Overflow**: The firmware's ring buffer (`codec_ring_buf`) had no overflow detection, causing silent data loss when the buffer filled up
2. **Backend Buffering Issues**: Simple bytearray buffers without proper overflow management led to time slippage
3. **Opus Frame Corruption**: No error recovery for corrupted audio frames, leading to audio artifacts

## Solution Overview

### Firmware Changes

**Enhanced Ring Buffer Management (`omi/firmware/omi/src/lib/dk2/transport.c`)**
- Added overflow detection before writing to ring buffer
- Implemented automatic cleanup of oldest packets when buffer is full
- Added comprehensive logging for debugging overflow events
- Added packet dropping statistics and monitoring

**Improved Error Handling (`omi/firmware/omi/src/main.c`)**
- Added error counting and consecutive error detection
- Implemented audio pipeline reset logic for persistent errors
- Enhanced logging with comprehensive metrics
- Added validation for NULL buffers

### Backend Changes

**Smart Audio Buffer Management (`backend/routers/pusher.py`)**
- Replaced simple bytearray with intelligent buffer management class
- Added timestamp tracking to prevent time slippage
- Implemented automatic cleanup of old data (>5 seconds)
- Added overflow detection and handling with proper error reporting

**Opus Frame Error Recovery (`backend/utils/audio.py`)**
- Added try-catch around Opus decoding with graceful error handling
- Implemented silence insertion for corrupted frames to maintain audio continuity
- Added comprehensive logging of corruption events
- Added frame corruption statistics

### Debug Tools

**Audio Debug Script (`scripts/debug_audio_issues.py`)**
- Packet timing analysis to detect slippage
- Overflow event detection and reporting
- Corruption event tracking
- Comprehensive debug reports for troubleshooting

## Testing

### Firmware Testing
- Built and flashed firmware to test device
- Monitored logs for overflow events and error handling
- Verified proper buffer management under load

### Backend Testing
- Tested audio buffer management with various data rates
- Verified Opus frame error recovery
- Confirmed time slippage prevention

### End-to-End Testing
- Connected omi device to smartphone
- Recorded multiple 10-second audio clips
- Verified no clicking sounds and accurate durations
- Confirmed improved audio quality

## Key Improvements

1. **Prevents Audio Data Loss**: Ring buffer overflow detection prevents silent data loss
2. **Eliminates Time Slippage**: Timestamp-based buffer management maintains audio timing
3. **Improves Error Recovery**: Graceful handling of corrupted Opus frames
4. **Enhanced Monitoring**: Comprehensive logging and metrics for debugging
5. **Better User Experience**: Eliminates clicking sounds and duration inconsistencies

## Configuration Recommendations

For optimal performance, consider adjusting these values based on connection quality:

```c
// In config.h - increase if overflow is frequent
#define AUDIO_BUFFER_SAMPLES 32000 // 2s instead of 1s
#define NETWORK_RING_BUF_SIZE 64   // Double the ring buffer size
```

```python
# In pusher.py - adjust buffer sizes based on connection quality
audio_buffer_manager = AudioBufferManager(max_buffer_size=sample_rate * 15)  # 15 seconds
```

## Monitoring

The implementation includes comprehensive monitoring capabilities:

- **Ring Buffer Overflow Count**: Should be 0 in normal operation
- **Audio Processing Errors**: Should be minimal
- **Time Slippage Events**: Should be 0
- **Opus Frame Corruption**: Should be minimal

## Related Issues

- Fixes #2165: Microphone Clicking & Time Slippage Issue
- Related to #2193: Inconsistent audio received from developer audiobytes webhook
- Builds on partial fix from #2158: sample webserver

## Breaking Changes

None. This is a backward-compatible fix that improves error handling and reliability.

## Checklist

- [x] Code follows the project's coding standards
- [x] Tests pass locally
- [x] Documentation updated
- [x] No breaking changes introduced
- [x] Error handling improved
- [x] Logging enhanced for debugging
- [x] Performance impact assessed (minimal)

## Screenshots

N/A - Audio quality improvements are not visually apparent but can be verified through testing.

---

This fix addresses the core issues causing audio clicking and time slippage while maintaining backward compatibility and improving the overall reliability of the audio processing pipeline. 