#ifndef SD_CARD_H
#define SD_CARD_H

#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>
#include <zephyr/kernel.h>

#define MAX_STORAGE_BYTES 0x1E000000 // 480MB
#define MAX_WRITE_SIZE 440
#define MAX_FILENAME_LEN 32
#define MAX_AUDIO_FILES 100
#define FILE_ROTATION_INTERVAL_MS (30 * 60 * 1000)  // 30 minutes in milliseconds

/* Request types for the SD worker */
typedef enum {
    REQ_CLEAR_AUDIO_DIR,
    REQ_WRITE_DATA,
    REQ_READ_DATA,
    REQ_SAVE_OFFSET,
    REQ_CREATE_NEW_FILE,
    REQ_GET_FILE_STATS,
    REQ_GET_FILE_LIST,
    REQ_DELETE_FILE,
} sd_req_type_t;

/* Read request response object */
struct read_resp {
    struct k_sem sem;
    int res;
    ssize_t read_bytes;
};

/* File statistics response */
struct file_stats_resp {
    struct k_sem sem;
    int res;
    uint32_t file_count;
    uint64_t total_size;
};

/* File list response */
struct file_list_resp {
    struct k_sem sem;
    int res;
    int count;
};

/* Offset info structure stored in info.txt */
typedef struct {
    char oldest_filename[MAX_FILENAME_LEN];   // Oldest file being read
    uint32_t offset_in_file;                  // Offset within that file
} sd_offset_info_t;

/* Generic request message passed to worker */
typedef struct {
    sd_req_type_t type;
    union {
        struct {
            uint8_t buf[MAX_WRITE_SIZE];
            size_t len;
            struct read_resp *resp;
        } write;
        struct {
            char filename[MAX_FILENAME_LEN];  // Specific file to read from
            uint32_t offset;
            uint32_t length;
            uint8_t *out_buf;
            struct read_resp *resp;
        } read;
        struct {
            sd_offset_info_t offset_info;
        } info;
        struct {
            struct read_resp *resp;
        } clear_dir;
        struct {
            struct read_resp *resp;
        } create_file;
        struct {
            struct file_stats_resp *resp;
        } file_stats;
        struct {
            char (*filenames)[MAX_FILENAME_LEN];
            int max_files;
            struct file_list_resp *resp;
        } file_list;
        struct {
            char filename[MAX_FILENAME_LEN];
            struct read_resp *resp;
        } delete_file;
    } u;
} sd_req_t;

/**
 * @brief Initialize the SD card module interface.
 *
 * @return 0 on success, negative error code otherwise.
 */
int app_sd_init(void);

/**
 * @brief Put the SD card interface (controller) into a low-power (suspend) state.
 *        Note: This typically suspends the SPI controller managing the SD card slot.
 *
 * @return 0 on success, negative error code on failure to suspend.
 */
int app_sd_off(void);

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE

/**
 * @brief Write to the current audio file specified by the write pointer
 *
 * @param data Buffer containing data to write
 * @param length Number of bytes to write
 * @return number of bytes written
 */
uint32_t write_to_file(uint8_t *data, uint32_t length);

/**
 * @brief Read from a specific audio file
 *
 * @param filename Name of the file to read from (e.g., "1234567890.txt")
 * @param buf Buffer to read data into
 * @param amount Number of bytes to read
 * @param offset Offset within the file to read from
 * @return number of bytes read, or negative error code
 */
int read_audio_data(const char *filename, uint8_t *buf, int amount, int offset);

/**
 * @brief Get the size of the current writing file
 * @return size of the file in bytes
 */
uint32_t get_file_size(void);

/**
 * @brief Get the name of the current writing file
 * @param buf Buffer to store the filename
 * @param buf_size Size of the buffer
 * @return 0 on success, negative error code otherwise
 */
int get_current_filename(char *buf, size_t buf_size);

/**
 * @brief Clear the audio directory.
 *
 * This deletes all audio files in the audio directory.
 * @return 0 if successful, negative errno code if error
 */
int clear_audio_directory(void);

/**
 * @brief Save the current offset info to the info file
 *
 * @param filename The oldest file being read
 * @param offset Offset within that file
 * @return 0 if successful, negative errno code if error
 */
int save_offset(const char *filename, uint32_t offset);

/**
 * @brief Get the saved offset info from the info file
 *
 * @param filename Buffer to store the oldest filename (must be at least MAX_FILENAME_LEN)
 * @param offset Pointer to store the offset value
 * @return 0 on success, negative errno code if error
 */
int get_offset(char *filename, uint32_t *offset);

/**
 * @brief Create a new audio file with current timestamp
 *
 * This forces creation of a new file, useful when BLE connection
 * has been active for a long time.
 * @return 0 if successful, negative errno code if error
 */
int create_new_audio_file(void);

/**
 * @brief Notify that BLE connection state has changed
 *
 * Call this when BLE connects/disconnects to manage file rotation.
 * @param connected true if BLE is now connected, false if disconnected
 */
void sd_notify_ble_state(bool connected);

/**
 * @brief Get file statistics
 *
 * @param file_count Pointer to store the number of audio files
 * @param total_size Pointer to store the total size of all audio files
 * @return 0 on success, negative error code otherwise
 */
int get_audio_file_stats(uint32_t *file_count, uint64_t *total_size);

/**
 * @brief Get list of audio files sorted by timestamp (oldest first)
 *
 * @param filenames Array of filename buffers
 * @param max_files Maximum number of files to retrieve
 * @param count Pointer to store the actual number of files found
 * @return 0 on success, negative error code otherwise
 */
int get_audio_file_list(char filenames[][MAX_FILENAME_LEN], int max_files, int *count);

/**
 * @brief Delete a specific audio file by name.
 *
 * If the file is currently being recorded to, the SD worker will stop
 * using it (flushing and closing), mark it as deleted, and the next
 * BLE disconnect will trigger creation of a new file.
 *
 * @param filename Name of the audio file to delete.
 * @return 0 on success, negative error code otherwise
 */
int delete_audio_file(const char *filename);

/**
 * @brief Update current audio filename after receiving time sync from BLE
 * 
 * When device boots without RTC time, it creates file with uptime-based name.
 * After receiving real timestamp from BLE, this function calculates the correct
 * timestamp and renames the file accordingly.
 * 
 * @param synced_utc_time The UTC timestamp received from BLE time sync
 */
void sd_update_filename_after_timesync(uint32_t synced_utc_time);

/**
 * @brief Turn on SD card power
 */
void sd_on(void);

/**
 * @brief Turn off SD card power
 */
void sd_off(void);

/**
 * @brief Check if SD card is powered on
 *
 * @return true if SD card is on, false otherwise
 */
bool is_sd_on(void);

#endif // CONFIG_OMI_ENABLE_OFFLINE_STORAGE

#endif // SD_CARD_H
