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
//private
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
 * 
 * 
 * @return number of bytes written
 */
int write_to_file(uint8_t *data,uint32_t length);

/**
 * @brief Read from the current audio file specified by the read pointer
 *
 * 
 * 
 * @return number of bytes read
 */
int read_audio_data(uint8_t *buf, int amount,int offset);
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
#endif
