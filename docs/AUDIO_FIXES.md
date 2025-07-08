# Audio Clicking & Time Slippage Fixes

This document describes the fixes implemented for issue #2165: "Microphone Clicking & Time Slippage Issue".

## Problem Summary

The omi device was experiencing:
1. **Persistent clicking noise** in audio recordings on multiple Omi Dev Kits
2. **Audio clip duration inconsistencies** (e.g., set for 10s, but files were 25–50s long)
3. **Opus frame decoding errors** suggesting data corruption
4. **Time slippage** due to backend buffering logic

## Root Causes Identified

### 1. Firmware Ring Buffer Overflow
- The firmware ring buffer (`codec_ring_buf`) had no overflow detection
- When buffer overflowed, data was silently lost, causing audio gaps
- No mechanism to handle backpressure from slow Bluetooth connections

### 2. Backend Buffering Issues
- Simple bytearray buffers without overflow management
- Fixed delay-based processing causing time slippage
- No handling of delayed or corrupted packets

### 3. Opus Frame Corruption
- No error recovery for corrupted Opus frames
- Silent failures leading to audio artifacts

## Fixes Implemented

### Firmware Fixes (`omi/firmware/omi/src/`)

#### 1. Ring Buffer Overflow Detection (`transport.c`)
```c
// Added overflow detection and management
static uint32_t ring_buffer_overflow_count = 0;
static uint32_t total_packets_dropped = 0;
static bool ring_buffer_overflow_detected = false;
```

**Changes:**
- Added overflow detection before writing to ring buffer
- Implemented automatic cleanup of oldest packets when buffer is full
- Added comprehensive logging for debugging

#### 2. Enhanced Error Handling (`main.c`)
```c
// Added error tracking
uint32_t audio_processing_errors = 0;
uint32_t consecutive_processing_errors = 0;
```

**Changes:**
- Added error counting and consecutive error detection
- Implemented audio pipeline reset logic for persistent errors
- Enhanced logging with error statistics

### Backend Fixes (`backend/`)

#### 1. Smart Audio Buffer Management (`routers/pusher.py`)
```python
class AudioBufferManager:
    def __init__(self, max_buffer_size: int = 1024 * 1024):
        self.max_buffer_size = max_buffer_size
        self.buffer = bytearray()
        self.timestamps = deque()  # Track when data was added
        self.overflow_count = 0
```

**Changes:**
- Replaced simple bytearray with intelligent buffer management
- Added timestamp tracking to prevent time slippage
- Implemented automatic cleanup of old data (>5 seconds)
- Added overflow detection and handling

#### 2. Opus Frame Error Recovery (`utils/audio.py`)
```python
try:
    decoded_pcm = opus_decoder.decode(encoded_packet)
    wave_write.writeframes(decoded_pcm)
except Exception as e:
    corrupted_frames += 1
    logger.warning(f"Failed to decode Opus frame {i}/{total_frames}: {e}")
    
    # Try to recover by inserting silence
    silence_frame = b'\x00' * (frame_rate * channels * sample_width // 50)
    wave_write.writeframes(silence_frame)
```

**Changes:**
- Added try-catch around Opus decoding
- Implemented silence insertion for corrupted frames
- Added comprehensive logging of corruption events

### Debug Tools

#### Audio Debug Script (`scripts/debug_audio_issues.py`)
```python
class AudioDebugger:
    def analyze_timing(self) -> Dict[str, Any]:
        # Analyze timing patterns to detect slippage
        # Detect potential time slippage (intervals much larger than expected)
```

**Features:**
- Packet timing analysis
- Overflow event detection
- Corruption event tracking
- Comprehensive debug reports

## Testing the Fixes

### 1. Firmware Testing
```bash
# Build and flash the firmware
cd omi/firmware/omi
west build -b nrf52840dk_nrf52840
west flash

# Monitor logs for overflow events
west log
```

**Expected Logs:**
- `Ring buffer getting full, available space: X bytes` (warning)
- `Ring buffer overflow! Dropped packet X, total dropped: Y` (error)
- `Dropped oldest packet to make space` (info)

### 2. Backend Testing
```bash
# Start the backend
cd backend
python main.py

# Run the debug script
cd scripts
python debug_audio_issues.py
```

**Expected Output:**
- No buffer overflow events
- Consistent timing intervals
- Proper error recovery for corrupted frames

### 3. End-to-End Testing
1. Connect omi device to smartphone
2. Record 10-second audio clip
3. Verify:
   - No clicking sounds
   - Accurate duration (10 seconds)
   - Clear audio quality
   - No Opus decoding errors in logs

## Configuration Recommendations

### Firmware Configuration (`config.h`)
```c
// Consider increasing buffer sizes if overflow is frequent
#define AUDIO_BUFFER_SAMPLES 32000 // 2s instead of 1s
#define NETWORK_RING_BUF_SIZE 64   // Double the ring buffer size
```

### Backend Configuration
```python
# Adjust buffer sizes based on connection quality
audio_buffer_manager = AudioBufferManager(max_buffer_size=sample_rate * 15)  # 15 seconds
```

## Monitoring and Metrics

### Key Metrics to Monitor
1. **Ring Buffer Overflow Count**: Should be 0 in normal operation
2. **Audio Processing Errors**: Should be minimal
3. **Time Slippage Events**: Should be 0
4. **Opus Frame Corruption**: Should be minimal

### Log Analysis
```bash
# Search for overflow events
grep "Ring buffer overflow" firmware.log

# Search for audio errors
grep "Failed to process PCM data" firmware.log

# Search for corruption events
grep "Failed to decode Opus frame" backend.log
```

## Future Improvements

1. **Adaptive Buffer Sizing**: Dynamically adjust buffer sizes based on connection quality
2. **Packet Loss Detection**: Implement sequence number tracking for missing packets
3. **Connection Quality Monitoring**: Track Bluetooth connection parameters
4. **Real-time Metrics**: Add real-time monitoring dashboard for audio quality

## Related Issues

- Issue #2165: Microphone Clicking & Time Slippage Issue
- PR #2158: sample webserver (partial fix)
- Issue #2193: Inconsistent audio received from developer audiobytes webhook

## Contributors

- @skywinder (issue reporter)
- @AnkushMalaker (partial fix contributor)
- [Your Name] (comprehensive fix implementation) 