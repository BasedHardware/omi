#ifndef SDCARD_H
#define SDCARD_H

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
int create_file(const char* file_path);

/**
 * @brief Generate a new audio file header
 *
 * Creates a standardized header for audio files that includes metadata
 * like file format, timestamp, and identifier.
 * 
 * @param num File number to include in the header
 * @return Pointer to generated header string
 */
char* generate_new_audio_header(uint8_t num);

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
 * Writes audio data to the current file at the current write position.
 * The file must be previously selected using move_write_pointer().
 * 
 * @param data Pointer to data buffer to write
 * @param length Number of bytes to write
 * @return number of bytes written
 */
int write_to_file(uint8_t *data,uint32_t length);

/**
 * @brief Read from the current audio file specified by the read pointer
 *
 * Reads audio data from the current file at the specified offset.
 * The file must be previously selected using move_read_pointer().
 * 
 * @param buf Buffer to store the read data
 * @param amount Number of bytes to read
 * @param offset Position in the file to read from
 * @return number of bytes read
 */
int read_audio_data(uint8_t *buf, int amount,int offset);

/**
 * @brief Get the size of the specified audio file number
 *
 * Returns the total size in bytes of the requested audio file.
 * 
 * @param num The audio file number to query
 * @return size of the file in bytes
 */
uint32_t get_file_size(uint8_t num);

/**
 * @brief Move the read pointer to the specified audio file position
 *
 * Sets the current read file to the specified audio file number.
 * Subsequent read operations will use this file.
 * 
 * @param num Audio file number to set as current read file
 * @return 0 if successful, negative errno code if error
 */
int move_read_pointer(uint8_t num);

/**
 * @brief Move the write pointer to the specified audio file position
 *
 * Sets the current write file to the specified audio file number.
 * Subsequent write operations will use this file.
 * 
 * @param num Audio file number to set as current write file
 * @return 0 if successful, negative errno code if error
 */
int move_write_pointer(uint8_t num);

/**
 * @brief Clear the specified audio file
 *
 * Erases all data in the specified audio file and resets it to
 * just contain the header.
 * 
 * @param num Audio file number to clear
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

/**
 * @brief Save the current offset position
 *
 * Stores the current file position offset to persistent storage
 * for resuming operations after power cycle.
 * 
 * @param offset The file offset to save
 * @return 0 if successful, negative errno code if error
 */
int save_offset(uint32_t offset);

/**
 * @brief Get the saved offset position
 *
 * Retrieves the previously saved file position offset.
 * 
 * @return The saved offset value
 */
int get_offset();

/**
 * @brief Power on the SD card interface
 *
 * Enables power to the SD card and prepares it for I/O operations.
 */
void sd_on();

/**
 * @brief Power off the SD card interface
 *
 * Disables power to the SD card to save energy when storage
 * operations are not needed.
 */
void sd_off();

/**
 * @brief Check if the SD card is powered on
 *
 * Reports whether the SD card interface is currently powered and active.
 * 
 * @return true if SD card is powered on, false otherwise
 */
bool is_sd_on();
#endif
