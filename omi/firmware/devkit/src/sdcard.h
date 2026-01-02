#ifndef SDCARD_H
#define SDCARD_H

#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>
#include <zephyr/kernel.h>

#define MAX_WRITE_SIZE 440

/* Request types for the SD worker */
typedef enum {
    REQ_CLEAR_AUDIO_DIR,
    REQ_WRITE_DATA,
    REQ_READ_DATA,
    REQ_SAVE_OFFSET,
    REQ_READ_OFFSET
} sd_req_type_t;

/* Read request response object */
struct read_resp {
    struct k_sem sem;
    int res;
    ssize_t read_bytes;
};

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
            uint32_t offset;
            uint32_t length;
            uint8_t *out_buf;
            struct read_resp *resp;
        } read;
        struct {
            uint32_t offset_value;
        } info;
        struct {
            struct read_resp *resp;
            uint32_t *out_offset;
        } offset;
        struct {
            struct read_resp *resp;
        } clear_dir;
    } u;
} sd_req_t;

// Maximum number of audio files supported (for backward compatibility)
#define MAX_AUDIO_FILES 24

/**
 * @brief Initialize the SD card worker thread.
 *
 * Starts the SD worker thread which handles all SD card operations.
 *
 * @return 0 if successful, negative errno code if error
 */
int sd_card_init(void);

/**
 * @brief Mount the SD Card. Initializes the audio files
 *
 * Mounts the SD Card and initializes the audio files. If the SD card does not contain those files, the
 * function will create them.
 *
 * @return 0 if successful, negative errno code if error
 * @deprecated Use sd_card_init() instead
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

// private - deprecated
char *generate_new_audio_header(uint8_t num);

/**
 * @brief Initialize an audio file of number 1
 *
 * Initializes an audio file. It will be called a nn.txt, where nn is the number of the file.
 *  example: initialize_audio_file(1) will create a file called a01.txt
 * @return 0 if successful, negative errno code if error
 * @deprecated Not needed with new single-file model
 */
int initialize_audio_file(uint8_t num);

/**
 * @brief Write to the current audio file specified by the write pointer
 *
 * @param data Buffer containing data to write
 * @param length Number of bytes to write
 * @return number of bytes written, or 0 on error
 */
uint32_t write_to_file(uint8_t *data, uint32_t length);

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
 * @brief Get the size of the current audio file
 *
 * @return size of the file in bytes
 */
uint32_t get_file_size(void);

/**
 * @brief Get the size of the specified audio file number (deprecated)
 *
 * @param num Audio file number (ignored, always returns file 1 size)
 * @return size of the file in bytes
 * @deprecated Use get_file_size() without parameter instead
 */
uint32_t get_file_size_num(uint8_t num);

/**
 * @brief Move the read pointer to the specified audio file position
 *
 * @param num Audio file number
 * @return 0 if successful, negative errno code if error
 * @deprecated Not needed with new single-file model
 */
int move_read_pointer(uint8_t num);

/**
 * @brief Move the write pointer to the specified audio file position
 *
 * @param num Audio file number
 * @return 0 if successful, negative errno code if error
 * @deprecated Not needed with new single-file model
 */
int move_write_pointer(uint8_t num);

/**
 * @brief Clear the specified audio file
 *
 * @param num Audio file number
 * @return 0 if successful, negative errno code if error
 * @deprecated Use clear_audio_directory() instead
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
 * @return offset value, or 0 if error
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

#endif
