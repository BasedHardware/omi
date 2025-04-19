/**
 * @file sdcard.c
 * @brief Implementation of SD card file system operations for audio storage
 *
 * This file implements operations for SD card initialization, mounting,
 * and file handling for audio data storage. It manages a directory structure
 * with audio files and provides file pointer operations for reading and writing.
 */
#include <ff.h>
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/fs/fs.h>
#include <zephyr/fs/fs_sys.h>
#include <zephyr/logging/log.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/check.h>
#include "sdcard.h"

LOG_MODULE_REGISTER(sdcard, CONFIG_LOG_DEFAULT_LEVEL);

/**
 * @brief FAT filesystem instance
 */
static FATFS fat_fs;

/**
 * @brief Mount point configuration structure
 * 
 * Defines filesystem type, associated data structure, and mount options.
 */
static struct fs_mount_t mount_point = {
	.type = FS_FATFS,
	.fs_data = &fat_fs,
};

/**
 * @brief GPIO specification for the SD card enable pin (P1.10)
 * 
 * Used to control power to the SD card for power management.
 * The SD card uses the following pins:
 * - SDSCK: P1.07
 * - SDMISO: P1.08
 * - SDMOSI: P1.09
 * - SDEN: P1.10
 * - SDCS: P1.11
 */
/* This line fetches the GPIO pin configuration from the devicetree:
 * - GPIO_DT_SPEC_GET_OR is a Zephyr macro that gets GPIO info from devicetree
 * - DT_NODELABEL(sdcard_en_pin) references the 'sdcard_en_pin' node defined in the DTS file
 *   which specifies this pin is on GPIO1.10 and active high
 * - gpios references the 'gpios' property in that node
 * - {0} provides a fallback value if the node/property isn't found
 * The resulting gpio_dt_spec struct contains the GPIO controller, pin number, and flags
 */
static const struct gpio_dt_spec sd_en_gpio_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

/**
 * @brief Current count of audio files
 */
uint8_t file_count = 0;

/**
 * @brief Maximum length for file paths
 */
#define MAX_PATH_LENGTH 32

/**
 * @brief Buffer for current file path
 */
static char current_full_path[MAX_PATH_LENGTH];

/**
 * @brief Buffer for current read file path
 */
static char read_buffer[MAX_PATH_LENGTH];

/**
 * @brief Buffer for current write file path
 */
static char write_buffer[MAX_PATH_LENGTH];

/**
 * @brief Array to store file sizes
 */
uint32_t file_num_array[2];    

/**
 * @brief SD card mount point path
 */
static const char *disk_mount_pt = "/SD:/";

/**
 * @brief Flag indicating whether the SD card is powered on
 */
bool sd_enabled = false;

/**
 * @brief Initialize and mount the SD card
 *
 * Configures the SD card enable pin, initializes the SD card controller,
 * mounts the filesystem, and sets up the audio directory structure.
 *
 * @return 0 on success, negative error code on failure
 */
int mount_sd_card(void)
{
    /* Initialize the SD card enable pin */
    if (gpio_is_ready_dt(&sd_en_gpio_pin)) 
    {
        LOG_INF("SD Enable Pin ready");
    }
    else 
    {
        LOG_ERR("Error setting up SD Enable Pin");
        return -1;
    }

    /* Configure the SD card enable pin and power on the card */
    int ret = gpio_pin_configure_dt(&sd_en_gpio_pin, GPIO_OUTPUT);
    if (ret) 
    {
        LOG_ERR("Error configuring SD Pin: %d", ret);
        return -1;
    }
    
    ret = gpio_pin_set_dt(&sd_en_gpio_pin, 1);
    if (ret) 
    {
        LOG_ERR("Error enabling SD power: %d", ret);
        return -1;
    }
    
    sd_enabled = true;
    
    /* Initialize the SD card driver */
    const char *disk_pdrv = "SD";  
    int err = disk_access_init(disk_pdrv); 
    LOG_INF("disk_access_init: %d", err);
    if (err) 
    {   
        /* Reattempt initialization after delay if first attempt fails */
        k_msleep(1000);
        err = disk_access_init(disk_pdrv); 
        if (err) 
        {
            LOG_ERR("disk_access_init failed");
            sd_off();
            return -1;
        }
    }

    /* Mount the SD card filesystem */
    mount_point.mnt_point = "/SD:";
    int res = fs_mount(&mount_point);
    if (res == FR_OK) 
    {
        LOG_INF("SD card mounted successfully");
    } 
    else 
    {
        LOG_ERR("f_mount failed: %d", res);
        return -1;
    }
    
    /* Create the audio directory if it doesn't exist */
    res = fs_mkdir("/SD:/audio");

    if (res == FR_OK) 
    {
        LOG_INF("audio directory created successfully");
        initialize_audio_file(1);
    }
    else if (res == FR_EXIST) 
    {
        LOG_INF("audio directory already exists");
    }
    else 
    {
        LOG_INF("audio directory creation failed: %d", res);
    }

    /* Open the audio directory and count existing files */
    struct fs_dir_t audio_dir_entry;
    fs_dir_t_init(&audio_dir_entry);
    err = fs_opendir(&audio_dir_entry, "/SD:/audio");
    if (err) 
    {
        LOG_ERR("error while opening directory %d", err);
        return -1;
    }
    LOG_INF("result of opendir: %d", err);
    
    /* Initialize the first audio file */
    initialize_audio_file(1);
    
    /* Count files in the directory */
    struct fs_dirent file_count_entry;
    file_count = get_file_contents(&audio_dir_entry, &file_count_entry);
    file_count = 1;
    if (file_count < 0) 
    {
        LOG_ERR("error getting file count");
        return -1;
    }

    fs_closedir(&audio_dir_entry);
    LOG_INF("new num files: %d", file_count);

    /* Set up read and write pointers */
    res = move_write_pointer(file_count); 
    if (res) 
    {
        LOG_ERR("error while moving the write pointer");
        return -1;
    }

    move_read_pointer(file_count);
    if (res) 
    {
        LOG_ERR("error while moving the reader pointer");
        return -1;
    }
    LOG_INF("file count: %d", file_count);
   
    /* Check if info file exists, create if not */
    struct fs_dirent info_file_entry;
    const char *info_path = "/SD:/info.txt";
    res = fs_stat(info_path, &info_file_entry);
    if (res) 
    {
        res = create_file("info.txt");
        save_offset(0);
        LOG_INF("result of info.txt creation: %d", res);
    }
    
    LOG_INF("result of check: %d", res);

	return 0;
}

/**
 * @brief Get the size of a specific audio file
 *
 * @param num The audio file number to query
 * @return Size of the file in bytes, 0 if error
 */
uint32_t get_file_size(uint8_t num)
{
    char *ptr = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, ptr);
    k_free(ptr);
    struct fs_dirent entry;
    int res = fs_stat(current_full_path, &entry);
    if (res)
    {
        LOG_ERR("invalid file in get file size");
        return 0;  
    }
    return (uint32_t)entry.size;
}

/**
 * @brief Set the current read file to the specified audio file
 *
 * @param num The audio file number to set as current read file
 * @return 0 on success, negative error code on failure
 */
int move_read_pointer(uint8_t num) 
{
    char *read_ptr = generate_new_audio_header(num);
    snprintf(read_buffer, sizeof(read_buffer), "%s%s", disk_mount_pt, read_ptr);
    k_free(read_ptr);
    struct fs_dirent entry; 
    int res = fs_stat(read_buffer, &entry);
    if (res) 
    {
        LOG_ERR("invalid file in move read ptr");
        return -1;  
    }
    return 0;
}

/**
 * @brief Set the current write file to the specified audio file
 *
 * @param num The audio file number to set as current write file
 * @return 0 on success, negative error code on failure
 */
int move_write_pointer(uint8_t num) 
{
    char *write_ptr = generate_new_audio_header(num);
    snprintf(write_buffer, sizeof(write_buffer), "%s%s", disk_mount_pt, write_ptr);
    k_free(write_ptr);
    struct fs_dirent entry;
    int res = fs_stat(write_buffer, &entry);
    if (res) 
    {
        LOG_ERR("invalid file in move write pointer");  
        return -1;  
    }
    return 0;   
}

/**
 * @brief Create a new file at the specified path
 *
 * @param file_path The path of the file to create (relative to mount point)
 * @return 0 on success, negative error code on failure
 */
int create_file(const char *file_path)
{
    int ret = 0;
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, file_path);
	struct fs_file_t data_file;
	fs_file_t_init(&data_file);
	ret = fs_open(&data_file, current_full_path, FS_O_WRITE | FS_O_CREATE);
	if (ret) 
	{
        LOG_ERR("File creation failed %d", ret);
		return -2;
	} 
    fs_close(&data_file);
    return 0;
}

/**
 * @brief Read data from the current read file
 *
 * @param buf Buffer to store the read data
 * @param amount Number of bytes to read
 * @param offset Position in the file to read from
 * @return Number of bytes read or negative error code
 */
int read_audio_data(uint8_t *buf, int amount, int offset) 
{
    struct fs_file_t read_file;
   	fs_file_t_init(&read_file); 
    uint8_t *temp_ptr = buf;

	int rc = fs_open(&read_file, read_buffer, FS_O_READ | FS_O_RDWR);
    rc = fs_seek(&read_file, offset, FS_SEEK_SET);
    rc = fs_read(&read_file, temp_ptr, amount);
  	fs_close(&read_file);

    return rc;
}

/**
 * @brief Write data to the current write file
 *
 * @param data Pointer to data buffer to write
 * @param length Number of bytes to write
 * @return 0 on success, negative error code on failure
 */
int write_to_file(uint8_t *data, uint32_t length)
{
    struct fs_file_t write_file;
	fs_file_t_init(&write_file);
    uint8_t *write_ptr = data;
   	fs_open(&write_file, write_buffer, FS_O_WRITE | FS_O_APPEND);
	fs_write(&write_file, write_ptr, length);
    fs_close(&write_file);
    return 0;
}
    
/**
 * @brief Initialize an audio file with the specified number
 *
 * @param num The audio file number to initialize
 * @return 0 on success, negative error code on failure
 */
int initialize_audio_file(uint8_t num) 
{
    char *header = generate_new_audio_header(num);
    if (header == NULL) 
    {
        return -1;
    }
    create_file(header);
    k_free(header);
    return 0;
}

/**
 * @brief Generate a filename for an audio file with the specified number
 *
 * @param num The audio file number (1-99)
 * @return Pointer to allocated string with filename, NULL if invalid number
 */
char* generate_new_audio_header(uint8_t num) 
{
    if (num > 99) return NULL;
    char *ptr_ = k_malloc(14);
    ptr_[0] = 'a';
    ptr_[1] = 'u';
    ptr_[2] = 'd';
    ptr_[3] = 'i';
    ptr_[4] = 'o';
    ptr_[5] = '/';
    ptr_[6] = 'a';
    ptr_[7] = 48 + (num / 10);
    ptr_[8] = 48 + (num % 10);
    ptr_[9] = '.';
    ptr_[10] = 't';
    ptr_[11] = 'x';
    ptr_[12] = 't';
    ptr_[13] = '\0';

    return ptr_;
}

/**
 * @brief Count and collect information about files in a directory
 *
 * @param zdp Directory handle
 * @param entry Dirent structure to populate
 * @return Number of files found or negative error code
 */
int get_file_contents(struct fs_dir_t *zdp, struct fs_dirent *entry) 
{
    if (zdp->mp->fs->readdir(zdp, entry)) 
    {
        return -1;
    }
    if (entry->name[0] == 0) 
    {
        return 0;
    }
    int count = 0;  
    file_num_array[count] = entry->size;
    LOG_INF("file numarray %d %d", count, file_num_array[count]);
    LOG_INF("file name is %s", entry->name);
    count++;
    while (zdp->mp->fs->readdir(zdp, entry) == 0) 
    {
        if (entry->name[0] == 0)
        {
            break;
        }
        file_num_array[count] = entry->size;
        LOG_INF("file numarray %d %d", count, file_num_array[count]);
        LOG_INF("file name is %s", entry->name);
        count++;
    }
    return count;
}

/**
 * @brief Clear an audio file (delete and recreate empty)
 *
 * @param num The audio file number to clear
 * @return 0 on success, negative error code on failure
 */
int clear_audio_file(uint8_t num) 
{
    char *clear_header = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, clear_header);
    k_free(clear_header);
    int res = fs_unlink(current_full_path);
    if (res) 
    {
        LOG_ERR("error deleting file");
        return -1;
    }

    char *create_file_header = generate_new_audio_header(num);
    k_msleep(10);
    res = create_file(create_file_header);
    k_free(create_file_header);
    if (res) 
    {
        LOG_ERR("error creating file");
        return -1;
    }

    return 0;
}

/**
 * @brief Delete an audio file
 *
 * @param num The audio file number to delete
 * @return 0 on success, negative error code on failure
 */
int delete_audio_file(uint8_t num) 
{
    char *ptr = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, ptr);
    k_free(ptr);
    int res = fs_unlink(current_full_path);
    if (res) 
    {
        LOG_PRINTK("error deleting file in delete");
        return -1;
    }

    return 0;
}

/**
 * @brief Clear the entire audio directory and reset to initial state
 *
 * @return 0 on success, negative error code on failure
 */
int clear_audio_directory() 
{
    if (file_count == 1) 
    {
        return 0;
    }
    
    int res = 0;
    for (uint8_t i = file_count; i > 0; i--) 
    {
        res = delete_audio_file(i);
        k_msleep(10);
        if (res) 
        {
            LOG_PRINTK("error on %d", i);
            return -1;
        }  
    }
    res = fs_unlink("/SD:/audio");
    if (res) 
    {
        LOG_ERR("error deleting file");
        return -1;
    }
    res = fs_mkdir("/SD:/audio");
    if (res) 
    {
        LOG_ERR("failed to make directory");
        return -1;
    }
    res = create_file("audio/a01.txt");
    if (res) 
    {
        LOG_ERR("failed to make new file in directory files");
        return -1;
    }
    LOG_ERR("done with clearing");

    file_count = 1;  
    move_write_pointer(1);
    return 0;
}

/**
 * @brief Save a file offset value to info.txt
 *
 * @param offset The offset value to save
 * @return 0 on success, negative error code on failure
 */
int save_offset(uint32_t offset)
{
    uint8_t buf[4] = {
        offset & 0xFF,
        (offset >> 8) & 0xFF,
        (offset >> 16) & 0xFF, 
        (offset >> 24) & 0xFF 
    };

    struct fs_file_t write_file;
    fs_file_t_init(&write_file);
    int res = fs_open(&write_file, "/SD:/info.txt", FS_O_WRITE | FS_O_CREATE);
    if (res) 
    {
        LOG_ERR("error opening file %d", res);
        return -1;
    }
    res = fs_write(&write_file, &buf, 4);
    if (res < 0)
    {
        LOG_ERR("error writing file %d", res);
        return -1;
    }
    fs_close(&write_file);
    return 0;
}

/**
 * @brief Get the saved offset value from info.txt
 *
 * @return The saved offset value or negative error code
 */
int get_offset()
{
    uint8_t buf[4];
    struct fs_file_t read_file;
    fs_file_t_init(&read_file);
    int rc = fs_open(&read_file, "/SD:/info.txt", FS_O_READ | FS_O_RDWR);
    if (rc < 0)
    {
        LOG_ERR("error opening file %d", rc);
        return -1;
    }
    rc = fs_seek(&read_file, 0, FS_SEEK_SET);
    if (rc < 0)
    {
        LOG_ERR("error seeking file %d", rc);
        return -1;
    }
    rc = fs_read(&read_file, &buf, 4);
    if (rc < 0)
    {
        LOG_ERR("error reading file %d", rc);
        return -1;
    }
    fs_close(&read_file);
    uint32_t *offset_ptr = (uint32_t*)buf;
    LOG_INF("get offset is %d", offset_ptr[0]);
    return offset_ptr[0];
}

/**
 * @brief Power off the SD card
 */
void sd_off()
{
    /* Power off the SD card to save energy */
    if (sd_enabled) {
        gpio_pin_set_dt(&sd_en_gpio_pin, 0);
        sd_enabled = false;
    }
}

/**
 * @brief Power on the SD card
 */
void sd_on()
{
    /* Power on the SD card for I/O operations */
    if (!sd_enabled) {
        gpio_pin_set_dt(&sd_en_gpio_pin, 1);
        sd_enabled = true;
    }
}

/**
 * @brief Check if the SD card is powered on
 *
 * @return true if SD card is powered on, false otherwise
 */
bool is_sd_on()
{
    return sd_enabled;
}
