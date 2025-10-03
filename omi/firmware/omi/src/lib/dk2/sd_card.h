#ifndef SD_H
#define SD_H

#include <stdbool.h>
#include <stdint.h>
#include <zephyr/kernel.h>

#define MAX_AUDIO_FILES 24                    // Max 24 files (482MB / 20MB)
#define MAX_FILE_SIZE_BYTES (1 * 1024 * 1024) // 20MB per file
#define AUDIO_FILE_PATH_PREFIX "/SD:/audio"

/**
 * @brief File metadata structure
 */
struct audio_file_metadata {
    uint8_t file_num;          // File number (1-based)
    uint32_t file_size;        // Current file size in bytes
    uint32_t start_offset_sec; // Start time offset in seconds from device boot
    uint32_t duration_sec;     // Duration of audio in seconds
    bool is_active;            // Whether this file is currently being written to
};

/**
 * @brief Initialize the SD card module interface.
 *
 * @return 0 on success, negative error code otherwise.
 */
int app_sd_init(void);

/**
 * @brief Mount the SD card and initialize audio directory
 *
 * @return 0 on success, negative error code otherwise.
 */
int app_sd_mount(void);

/**
 * @brief Unmount the SD card
 *
 * @return 0 on success, negative error code otherwise.
 */
int app_sd_unmount(void);

/**
 * @brief Put the SD card interface (controller) into a low-power (suspend) state.
 *        Note: This typically suspends the SPI controller managing the SD card slot.
 *
 * @return 0 on success, negative error code on failure to suspend.
 */
int app_sd_off(void);

/**
 * @brief Write audio data to current active file. Handles file rotation automatically.
 *
 * @param data Pointer to audio data buffer
 * @param length Length of data in bytes
 * @param current_time_sec Current time offset in seconds from device boot
 * @return Number of bytes written, negative on error
 */
int app_sd_write_audio(uint8_t *data, uint32_t length, uint32_t current_time_sec);

/**
 * @brief Read audio data from specified file
 *
 * @param file_num File number to read from (1-based)
 * @param buf Buffer to read into
 * @param length Number of bytes to read
 * @param offset Offset in file to read from
 * @return Number of bytes read, negative on error
 */
int app_sd_read_audio(uint8_t file_num, uint8_t *buf, uint32_t length, uint32_t offset);

/**
 * @brief Get metadata for all audio files
 *
 * @param metadata_array Array to store metadata (caller allocates)
 * @param max_count Maximum number of entries in array
 * @return Number of files found, negative on error
 */
int app_sd_get_file_list(struct audio_file_metadata *metadata_array, uint8_t max_count);

/**
 * @brief Delete a specific audio file
 *
 * @param file_num File number to delete (1-based)
 * @return 0 on success, negative on error
 */
int app_sd_delete_file(uint8_t file_num);

/**
 * @brief Delete all audio files
 *
 * @return 0 on success, negative on error
 */
int app_sd_delete_all_files(void);

/**
 * @brief Save base timestamp (from app connection) to SD card
 *
 * @param timestamp_ms Base timestamp in milliseconds (Unix epoch from app)
 * @return 0 on success, negative on error
 */
int app_sd_save_base_timestamp(uint64_t timestamp_ms);

/**
 * @brief Get saved base timestamp
 *
 * @param timestamp_ms Pointer to store timestamp
 * @return 0 on success, negative on error
 */
int app_sd_get_base_timestamp(uint64_t *timestamp_ms);

/**
 * @brief Check if SD card is currently mounted and ready
 *
 * @return true if ready, false otherwise
 */
bool app_sd_is_ready(void);

/**
 * @brief Check if SD card is writable (has free space and permissions)
 *
 * @return true if writable, false otherwise
 */
bool app_sd_is_writable(void);

#endif // SD_H
