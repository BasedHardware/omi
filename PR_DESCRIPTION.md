# Use smaller files on the SD card ($1500)

/claim #1650

## Summary

Implements time-based chunking for SD card audio files to reduce battery consumption when the device is disconnected. The firmware now creates 5-minute chunk files with timestamps instead of writing one large file.

## Changes

### Firmware (`omi/firmware/omi/src/sd_card.c`)

- **Added time-based chunking**: Creates new files every 5 minutes (300 seconds) when device is disconnected
- **Instantaneous mode switching**: 
  - Detects disconnection immediately via transport layer callback
  - Flushes any pending batch data before switching modes
  - Creates first chunk file immediately upon disconnection (no delay)
  - Periodic checks (every 500ms) ensure mode switches even when idle
- **Automatic mode switching**: Switches between:
  - **Connected mode**: Writes to single file `/SD:/audio/a01.txt` (backward compatible)
  - **Disconnected mode**: Writes to timestamped chunk files `/SD:/audio/audio_<timestamp>.bin`
- **Unique filenames**: Each chunk file uses persistent counter + uptime for uniqueness: `audio_<counter>_<uptime>.bin`
  - Persistent counter stored in info.txt prevents filename collisions after device reboot
  - Uptime suffix provides additional uniqueness within the same session
- **Error handling**: Fixed error recovery to use correct file path in chunking mode

### App (`app/lib/services/wals.dart`)

- **Updated chunk size**: Changed `sdcardChunkSizeSecs` from 60 to 300 seconds (5 minutes) to align with firmware chunking
- **Synchronized chunking**: App now syncs audio data in 5-minute chunks, matching the firmware's chunk file creation
- Added documentation explaining chunked file behavior
- Maintains backward compatibility with existing single-file storage interface

### Documentation

- Created `TEST_CHUNKING_FEATURE.md` with comprehensive testing guide

## Key Features

✅ **5-minute chunk files**: New file created every 300 seconds when disconnected  
✅ **Unique filenames**: Each file named `audio_<counter>_<uptime>.bin` (persistent counter prevents collisions)  
✅ **Instantaneous switching**: Mode switches immediately on disconnection (no delay)  
✅ **Automatic detection**: Switches to chunking mode when Bluetooth disconnected  
✅ **Data integrity**: Flushes pending data before mode switches to prevent data loss  
✅ **Synchronized app chunking**: App syncs in 5-minute chunks to align with firmware chunking  
✅ **Backward compatible**: Uses single file when connected (existing behavior)  
✅ **Battery efficient**: Smaller files = faster writes = reduced battery consumption  

## Testing

See `TEST_CHUNKING_FEATURE.md` for detailed testing instructions.

### Quick Test:
1. Flash firmware to device
2. Start recording while connected → writes to `a01.txt`
3. Disconnect device (turn off Bluetooth)
4. Continue recording for 6+ minutes
5. Verify: Multiple `audio_<counter>_<uptime>.bin` files created on SD card (one per 5 minutes)

## Technical Details

- **Chunk duration**: 300 seconds (5 minutes) - configurable via `CHUNK_DURATION_SECONDS`
- **File format**: Binary files with `.bin` extension
- **Filename generation**: Uses persistent counter (stored in info.txt) + uptime for unique filenames
  - Counter prevents collisions after device reboot
  - Info file structure: [offset: 4 bytes][chunk_counter: 4 bytes]
- **Mode detection**: 
  - Immediate detection via transport layer disconnection callback
  - Periodic checks (500ms) in worker thread when idle
  - Checks `get_current_connection()` returning NULL to detect disconnection
- **Instantaneous switching**: 
  - `sd_check_chunking_mode()` function called from transport layer on disconnection
  - Pending batch data is flushed immediately before mode switch
  - First chunk file created instantly, no waiting for next write
- **Performance optimization**: 
  - Removed redundant `update_chunking_mode()` call from write path
  - Mode switching handled via `REQ_CHECK_CHUNKING_MODE` and periodic checks only

## Related Issue

Fixes #1650

## Notes

- The app syncs data in 5-minute chunks (300 seconds) to align with the firmware's chunk file creation
- This ensures that when firmware creates chunked files, the app syncs them in corresponding 5-minute periods
- Chunked files are created on SD card with timestamps and can be accessed directly
- The storage interface maintains backward compatibility with the single-file mode when connected
