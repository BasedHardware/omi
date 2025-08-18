#ifndef SDCARD_CONFIG_H
#define SDCARD_CONFIG_H

/**
 * @file sdcard_config.h
 * @brief SD Card configuration constants
 * 
 * Centralizes all SD card related paths and configuration to avoid hardcoded values
 * throughout the codebase and make the system more configurable.
 */

// SD Card mount point and base paths
#define SDCARD_MOUNT_POINT "/SD:/"
#define SDCARD_AUDIO_DIR "audio"
#define SDCARD_AUDIO_PATH SDCARD_MOUNT_POINT SDCARD_AUDIO_DIR

// Configuration files
#define SDCARD_CHUNK_COUNTER_FILE SDCARD_MOUNT_POINT "chunk_counter.txt"
#define SDCARD_INFO_FILE SDCARD_MOUNT_POINT "info.txt"

// Chunking configuration
#define CHUNK_DURATION_CYCLES  40  // 600  // 5 minutes = 600 cycles of 500ms each
#define CHUNK_FILENAME_MAX_LENGTH 64
#define CHUNK_FILENAME_FORMAT "audio/chunk_%02d%02d%02d_%05d.bin"

// File system configuration
#define MAX_PATH_LENGTH 32
#define MAX_WRITE_SIZE 512  // Adjust based on your system's requirements

// Error codes (using negative values to match errno convention)
#define SDCARD_ERR_CHUNKING_DISABLED   -200
#define SDCARD_ERR_SD_NOT_ENABLED     -201
#define SDCARD_ERR_SYSTEM_BOOTING     -202
#define SDCARD_ERR_FILENAME_GENERATION -203
#define SDCARD_ERR_CHUNK_COUNTER      -204
#define SDCARD_ERR_FILE_CREATION      -205

#endif // SDCARD_CONFIG_H
