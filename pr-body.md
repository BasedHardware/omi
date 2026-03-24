## Problem

When WebSocket connection dropped mid-recording, audio frames were silently dropped instead of being buffered for later sync. This broke the core 'capture everything' promise.

**Related Issues:**
- Fixes #5913
- Fixes #5909

## Root Causes

1. **In streamAudioToWs**: `onByteStream()` was only called when `_isWalSupported` was true, which required Omi/OpenGlass + Opus codec. For other devices, audio was dropped when socket disconnected.

2. **In streamRecording (phone mic)**: No offline buffering existed at all.

3. **In _flushSystemAudioBuffer**: System audio also had no offline buffering.

## Fix

1. **streamAudioToWs**: Always buffer to WAL when socket is disconnected, regardless of device type or codec. Only mark frames as synced for WAL-reliability devices (Omi/OpenGlass with Opus).

2. **streamRecording**: Initialize WAL for phone recording and buffer to WAL when socket is disconnected.

3. **_flushSystemAudioBuffer**: Buffer accumulated audio to WAL when socket is disconnected.

This ensures audio is never lost during connection drops - it will be buffered locally and synced when connection is restored.
