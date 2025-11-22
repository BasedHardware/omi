#ifndef SD_CARD_H
#define SD_CARD_H

#include <stdbool.h>
#include <stdint.h>
#include <zephyr/kernel.h>

#define MAX_STORAGE_BYTES 0x1E000000 // 480MB

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

// Maximum number of audio files supported
#define MAX_AUDIO_FILES 24

// Global variables for offline storage
extern uint8_t file_count;
extern uint32_t file_num_array[MAX_AUDIO_FILES];

/**
 * @brief Create a file
 *
 * Creates a file at the given path
 *
 * @return 0 if successful, negative errno code if error
 */
int create_file(const char *file_path);

/**
 * @brief Generate a new audio file header/path
 *
 * @param num File number (1-99)
 * @return Allocated string with path like "audio/a01.txt", must be freed by caller
 */
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
 * @param data Buffer containing data to write
 * @param length Number of bytes to write
 * @return number of bytes written
 */
int write_to_file(uint8_t *data, uint32_t length);

/**
 * @brief Read from the current audio file specified by the read pointer
 *
 * @param buf Buffer to read data into
 * @param amount Number of bytes to read
 * @param offset Offset within the file to read from
 * @return number of bytes read
 */
int read_audio_data(uint8_t *buf, int amount, int offset);

/**
 * @brief Get the size of the specified audio file number
 *
 * @param num Audio file number
 * @return size of the file in bytes
 */
uint32_t get_file_size(uint8_t num);

/**
 * @brief Move the read pointer to the specified audio file position
 *
 * @param num Audio file number
 * @return 0 if successful, negative errno code if error
 */
int move_read_pointer(uint8_t num);

/**
 * @brief Move the write pointer to the specified audio file position
 *
 * @param num Audio file number
 * @return 0 if successful, negative errno code if error
 */
int move_write_pointer(uint8_t num);

/**
 * @brief Clear the specified audio file
 *
 * @param num Audio file number
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
int clear_audio_directory(void);

/**
 * @brief Save the current offset to the info file
 *
 * @param offset Offset value to save
 * @return 0 if successful, negative errno code if error
 */
int save_offset(uint32_t offset);

/**
 * @brief Get the saved offset from the info file
 *
 * @return offset value, or negative errno code if error
 */
uint32_t get_offset(void);

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
