#ifndef SDCARD_H
#define SDCARD_H

#include <stdbool.h>
#include <stdint.h>
#include "sdcard_config.h"

/**
 * @brief Mount the SD Card. Initializes the audio files
 *
 * Mounts the SD Card and initializes the audio files. If the SD card does not contain those files, the
 * function will create them.
 *
 * @return 0 if successful, negative errno code if error
 */
int mount_sd_card(void);

/**
 * @brief Create a file
 *
 * Creates a file at the given path
 *
 * @return 0 if successful, negative errno code if error
 */
int create_file(const char *file_path);
// private
char *generate_new_audio_header(uint8_t num);

/**
 * @brief Initialize an audio file of number 1
 *
 * Initializes an audio file. It will be called a nn.txt, where nn is the number of the file.
 *  example: initialize_audio_file(1) will create a file called a01.txt
 * @return 0 if successful, negative errno code if error
 */
int initialize_audio_file(uint8_t num);

/**
 * @brief Write to the current audio file specified by the write pointer
 *
 *
 *
 * @return number of bytes written
 */
int write_to_file(uint8_t *data, uint32_t length);

/**
 * @brief Read from the current audio file specified by the read pointer
 *
 *
 *
 * @return number of bytes read
 */
int read_audio_data(uint8_t *buf, int amount, int offset);
/**
 * @brief Get the size of the specified audio file number
 *
 *
 *
 * @return size of the file in bytes
 */
uint32_t get_file_size(uint8_t num);

/**
 * @brief Move the read pointer to the specified audio file position
 *
 *
 *
 * @return 0 if successful, negative errno code if error
 */
int move_read_pointer(uint8_t num);

/**
 * @brief Move the write pointer to the specified audio file position
 *
 *
 *
 * @return 0 if successful, negative errno code if error
 */
int move_write_pointer(uint8_t num);

/**
 * @brief Clear the specified audio file
 *
 *
 *
 * @return 0 if successful, negative errno code if error
 */
int clear_audio_file(uint8_t num);

/**
 * @brief Clear the audio directory.
 *
 * This deletes all audio files and leaves the audio directory with only one file left, a01.txt.
 * This automatically moves the read and write pointers to a01.txt.
 * @return 0 if successful, negative errno code if error
 */
int clear_audio_directory();

int save_offset(uint32_t offset);
int get_offset();

void sd_on();
void sd_off();

bool is_sd_on();

/**
 * @brief Global variable indicating if chunk recording is active
 */
extern bool chunk_active;

/**
 * @brief Global flag to enable/disable chunking system
 * Controlled by CONFIG_OMI_ENABLE_AUDIO_CHUNKING in project configuration
 * Set to false to use legacy file system, true for chunking
 */
extern bool chunking_enabled;

/**
 * @brief Generate a sequential audio file name
 *
 * Creates a file name with persistent counter for chunked recording
 * Format: audio/chunk_NNNNN.bin (where NNNNN is the persistent counter)
 * 
 * @return dynamically allocated string with file path, must be freed with k_free()
 */
char* generate_chunk_audio_filename(void);

/**
 * @brief Initialize a new chunk file for recording
 *
 * Creates a new audio file with sequential chunk naming for 5-minute chunks
 * 
 * @return 0 if successful, negative errno code if error
 */
int initialize_chunk_file(void);

/**
 * @brief Check if current chunk should be rotated
 *
 * 
 * @return true if chunk should be rotated, false otherwise
 */
bool should_rotate_chunk(void);

/**
 * @brief Check chunk rotation timing using cycle counter
 *
 * Should be called every 500ms from main loop.
 * Uses simple counter instead of k_uptime_get() for maximum efficiency.
 * Counts 500ms cycles and rotates after 600 cycles (5 minutes).
 */
void check_chunk_rotation_timing(void);

/**
 * @brief Start a new recording chunk
 *
 * Finalizes current chunk and starts a new one with timestamp-based naming
 * 
 * @return 0 if successful, negative errno code if error
 */
int start_new_chunk(void);

/**
 * @brief Mark system boot as complete to enable chunking
 *
 * Should be called after all system initialization is complete
 */
void set_system_boot_complete(void);

/**
 * @brief Save chunk counter to persistent storage
 *
 * Saves the current chunk counter value to SD card for persistence across reboots
 * 
 * @param counter The counter value to save
 * @return 0 if successful, negative errno code if error
 */
int save_chunk_counters(uint32_t start_counter, uint32_t current_counter);

/**
 * @brief Load chunk counter from persistent storage
 *
 * Loads the chunk counter value from SD card, returns 0 if file doesn't exist
 * 
 * @return The loaded counter value, or 0 if file doesn't exist or on error
 */
/**
 * @brief Get the persistent chunk counter value
 * 
 * @param counter Pointer to store the counter value
 * @return 0 if successful, negative errno code if error
 */
int get_chunk_counters(uint32_t *start_counter, uint32_t *current_counter);

/**
 * @brief Get the in-memory snapshot of chunk counters
 *
 * Reads the current values tracked by the chunking system without touching
 * persistent storage. Returns zeros when chunking is disabled.
 *
 * @param start_counter Pointer to receive the start counter value
 * @param current_counter Pointer to receive the current counter value
 */
void get_chunk_counter_snapshot(uint32_t *start_counter, uint32_t *current_counter);

#endif
