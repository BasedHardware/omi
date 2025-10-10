#include "sdcard.h"

#include <ff.h>
#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/fs/fs.h>
#include <zephyr/fs/fs_sys.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/check.h>
#include <zephyr/sys/atomic.h>
#include <string.h>
#include "sdcard_config.h"

LOG_MODULE_REGISTER(sdcard, CONFIG_LOG_DEFAULT_LEVEL);

static FATFS fat_fs;

static struct fs_mount_t mount_point = {
    .type = FS_FATFS,
    .fs_data = &fat_fs,
};

struct gpio_dt_spec sd_en_gpio_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio0)),
                                      .pin = 19,
                                      .dt_flags = GPIO_INT_DISABLE};

uint8_t file_count = 0;

static char current_full_path[MAX_PATH_LENGTH];
static char read_buffer[MAX_PATH_LENGTH];
static char write_buffer[MAX_PATH_LENGTH];

uint32_t file_num_array[2];

static const char *disk_mount_pt = SDCARD_MOUNT_POINT;

bool sd_enabled = false;

// Chunking variables
static char current_chunk_filename[CHUNK_FILENAME_MAX_LENGTH];
bool chunk_active = false;  // Made non-static for external access
static bool system_boot_complete = false;  // Prevent chunking during boot
// Chunking enabled flag - controlled by CONFIG_OMI_ENABLE_AUDIO_CHUNKING
#ifdef CONFIG_OMI_ENABLE_AUDIO_CHUNKING
bool chunking_enabled = true;
#else
bool chunking_enabled = false;
#endif
static atomic_t chunk_cycle_counter = ATOMIC_INIT(0);  // Thread-safe counter for 500ms cycles

// Persistent chunk counters for unique filenames across reboots
static uint32_t chunk_start_counter = 0;
static uint32_t chunk_current_counter = 0;

static atomic_t should_rotate_flag = ATOMIC_INIT(0);  // Thread-safe flag (0=false, 1=true)

// Forward declarations
int get_file_contents(struct fs_dir_t *zdp, struct fs_dirent *entry);

int mount_sd_card(void)
{
    // initialize the sd card enable pin (v2)
    if (gpio_is_ready_dt(&sd_en_gpio_pin)) {
        LOG_INF("SD Enable Pin ready");
    } else {
        LOG_ERR("Error setting up SD Enable Pin");
        return -1;
    }

    if (gpio_pin_configure_dt(&sd_en_gpio_pin, GPIO_OUTPUT_ACTIVE) < 0) {
        LOG_ERR("Error setting up SD Pin");
        return -1;
    }
    sd_enabled = true;

    // initialize the sd card
    const char *disk_pdrv = "SD";
    int err = disk_access_init(disk_pdrv);
    LOG_INF("disk_access_init: %d\n", err);
    if (err) { // reattempt
        k_msleep(1000);
        err = disk_access_init(disk_pdrv);
        if (err) {
            LOG_ERR("disk_access_init failed");
            return -1;
        }
    }

    mount_point.mnt_point = "/SD:";
    int res = fs_mount(&mount_point);
    if (res == FR_OK) {
        LOG_INF("SD card mounted successfully");
    } else {
        LOG_ERR("f_mount failed: %d", res);
        return -1;
    }
    
    res = fs_mkdir(SDCARD_AUDIO_PATH);

    if (res == FR_OK) {
        LOG_INF("audio directory created successfully");
        initialize_audio_file(1);
    } else if (res == FR_EXIST || res == -17) {
        LOG_INF("audio directory already exists");
    } else {
        LOG_INF("audio directory creation failed: %d", res);
    }

    if (chunking_enabled) {
        // ======================================================================
        // NEW CHUNKING SYSTEM
        // ======================================================================
        // This is the new audio chunk recording system that creates time-based
        // chunks for better power management.
        LOG_INF("Using chunking system");
        file_count = 1;  // Set to 1 for compatibility
        
        // Load the persistent chunk counters
        int ret = get_chunk_counters(&chunk_start_counter, &chunk_current_counter);
        if (ret < 0) {
            LOG_ERR("Failed to load chunk counters: %d", ret);
            chunk_start_counter = 0;
            chunk_current_counter = 0;
        }
        LOG_INF("Loaded chunk counters: start=%d current=%d", chunk_start_counter, chunk_current_counter);
    } else {
        // ======================================================================
        // LEGACY AUDIO FILE SYSTEM 
        // ======================================================================
        // This is the old file system that uses numbered file (a01.txt)
        // It is maintained for backward compatibility but should be removed
        // in future versions once chunking is fully validated.
        // TODO: Remove this legacy system in a future release
        LOG_INF("Using legacy file system (DEPRECATED)");
        struct fs_dir_t audio_dir_entry;
        fs_dir_t_init(&audio_dir_entry);
        err = fs_opendir(&audio_dir_entry, SDCARD_AUDIO_PATH);
        if (err) 
        {
            LOG_ERR("error while opening directory: %d", err);
            return -1;
        }
        LOG_INF("result of opendir: %d",err);
        initialize_audio_file(1);
        file_count = 1;
        if (file_count < 0) 
        {
            LOG_ERR(" error getting file count");
            return -1;
        }

        fs_closedir(&audio_dir_entry);
        LOG_INF("new num files: %d",file_count);

        res = move_write_pointer(file_count); 
        if (res) 
        {
            LOG_ERR("erro while moving the write pointer");
            return -1;
        }

        move_read_pointer(file_count);
        if (res) 
        {
            LOG_ERR("error while moving the reader pointer\n");
            return -1;
        }
        LOG_INF("file count: %d",file_count);
    }

    struct fs_dirent info_file_entry; //check if the info file exists. if not, generate new info file
    const char *info_path = SDCARD_INFO_FILE;
    res = fs_stat(info_path, &info_file_entry); // for later
    if (res) {
        res = create_file("info.txt");
        save_offset(0);
        LOG_INF("result of info.txt creation: %d", res);
    }
    
    LOG_INF("SD card mount completed");
	return 0;
}

uint32_t get_file_size(uint8_t num)
{
    char *ptr = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, ptr);
    k_free(ptr);
    struct fs_dirent entry;
    int res = fs_stat(&current_full_path, &entry);
    if (res) {
        LOG_ERR("invalid file in get file size\n");
        return 0;
    }
    return (uint32_t) entry.size;
}

int move_read_pointer(uint8_t num)
{
    char *read_ptr = generate_new_audio_header(num);
    snprintf(read_buffer, sizeof(read_buffer), "%s%s", disk_mount_pt, read_ptr);
    k_free(read_ptr);
    struct fs_dirent entry;
    int res = fs_stat(&read_buffer, &entry);
    if (res) {
        LOG_ERR("invalid file in move read ptr\n");
        return -1;
    }
    return 0;
}

int move_write_pointer(uint8_t num)
{
    char *write_ptr = generate_new_audio_header(num);
    snprintf(write_buffer, sizeof(write_buffer), "%s%s", disk_mount_pt, write_ptr);
    k_free(write_ptr);
    struct fs_dirent entry;
    int res = fs_stat(&write_buffer, &entry);
    if (res) {
        LOG_ERR("invalid file in move write pointer\n");
        return -1;
    }
    return 0;
}

int create_file(const char *file_path)
{
    int ret = 0;
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, file_path);
    struct fs_file_t data_file;
    fs_file_t_init(&data_file);
    ret = fs_open(&data_file, current_full_path, FS_O_WRITE | FS_O_CREATE);
    if (ret) {
        LOG_ERR("File creation failed %d", ret);
        return -2;
    }
    fs_close(&data_file);
    return 0;
}

int read_audio_data(uint8_t *buf, int amount, int offset)
{
    struct fs_file_t read_file;
   	fs_file_t_init(&read_file); 
    uint8_t *temp_ptr = buf;

    int rc = fs_open(&read_file, read_buffer, FS_O_READ | FS_O_RDWR);
    rc = fs_seek(&read_file, offset, FS_SEEK_SET);
    rc = fs_read(&read_file, temp_ptr, amount);
    // LOG_PRINTK("read data :");
    // for (int i = 0; i < amount;i++) {
    //     LOG_PRINTK("%d ",temp_ptr[i]);
    // }
    // LOG_PRINTK("\n");
    fs_close(&read_file);

    return rc;
}

int write_to_file(uint8_t *data, uint32_t length)
{
    struct fs_file_t write_file;
    fs_file_t_init(&write_file);
    uint8_t *write_ptr = data;
    
    int ret = fs_open(&write_file, write_buffer, FS_O_WRITE | FS_O_APPEND);
    if (ret < 0) {
        LOG_ERR("Failed to open file for writing: %d", ret);
        return ret;
    }
    
    ret = fs_write(&write_file, write_ptr, length);
    fs_close(&write_file);
    
    if (ret < 0) {
        LOG_ERR("Failed to write to file: %d", ret);
        return ret;
    }
    
    // Return number of bytes written (positive value) or error (negative)
    return ret;
}

int initialize_audio_file(uint8_t num)
{
    char *header = generate_new_audio_header(num);
    if (header == NULL) {
        return -1;
    }
    create_file(header);
    k_free(header);
    return 0;
}

char *generate_new_audio_header(uint8_t num)
{
    if (num > 99)
        return NULL;
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

int get_file_contents(struct fs_dir_t *zdp, struct fs_dirent *entry)
{
    if (zdp->mp->fs->readdir(zdp, entry)) {
        return -1;
    }
    if (entry->name[0] == 0) {
        return 0;
    }
    int count = 0;
    file_num_array[count] = entry->size;
    LOG_INF("file numarray %d %d ", count, file_num_array[count]);
    LOG_INF("file name is %s ", entry->name);
    count++;
    while (zdp->mp->fs->readdir(zdp, entry) == 0) {
        if (entry->name[0] == 0) {
            break;
        }
        file_num_array[count] = entry->size;
        LOG_INF("file numarray %d %d ", count, file_num_array[count]);
        LOG_INF("file name is %s ", entry->name);
        count++;
    }
    return count;
}
// we should clear instead of delete since we lose fifo structure
int clear_audio_file(uint8_t num)
{
    char *clear_header = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, clear_header);
    k_free(clear_header);
    int res = fs_unlink(current_full_path);
    if (res) {
        LOG_ERR("error deleting file");
        return -1;
    }

    char *create_file_header = generate_new_audio_header(num);
    k_msleep(10);
    res = create_file(create_file_header);
    k_free(create_file_header);
    if (res) {
        LOG_ERR("error creating file");
        return -1;
    }

    return 0;
}

int delete_audio_file(uint8_t num)
{
    char *ptr = generate_new_audio_header(num);
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, ptr);
    k_free(ptr);
    int res = fs_unlink(current_full_path);
    if (res) {
        LOG_PRINTK("error deleting file in delete\n");
        return -1;
    }

    return 0;
}
// the nuclear option.
int clear_audio_directory()
{
    if (file_count == 1) {
        return 0;
    }
    // check if all files are zero
    //  char* path_ = "/SD:/audio";
    //  clear_audio_file(file_count);
    int res = 0;
    for (uint8_t i = file_count; i > 0; i--) {
        res = delete_audio_file(i);
        k_msleep(10);
        if (res) {
            LOG_PRINTK("error on %d\n", i);
            return -1;
        }
    }
    res = fs_unlink(SDCARD_AUDIO_PATH);
    if (res) {
        LOG_ERR("error deleting file");
        return -1;
    }
    res = fs_mkdir(SDCARD_AUDIO_PATH);
    if (res) {
        LOG_ERR("failed to make directory");
        return -1;
    }
    res = create_file("audio/a01.txt");
    if (res) {
        LOG_ERR("failed to make new file in directory files");
        return -1;
    }
    LOG_ERR("done with clearing");

    file_count = 1;
    move_write_pointer(1);
    return 0;
    // if files are cleared, then directory is oked for destrcution.
}

int save_offset(uint32_t offset)
{
    uint8_t buf[4] = {offset & 0xFF, (offset >> 8) & 0xFF, (offset >> 16) & 0xFF, (offset >> 24) & 0xFF};

    struct fs_file_t write_file;
    fs_file_t_init(&write_file);
    int res = fs_open(&write_file, SDCARD_INFO_FILE, FS_O_WRITE | FS_O_CREATE);
    if (res) {
        LOG_ERR("error opening file %d", res);
        return -1;
    }
    res = fs_write(&write_file, &buf, 4);
    if (res < 0) {
        LOG_ERR("error writing file %d", res);
        return -1;
    }
    fs_close(&write_file);
    return 0;
}

int get_offset()
{
    uint8_t buf[4];
    struct fs_file_t read_file;
    fs_file_t_init(&read_file);
    int rc = fs_open(&read_file, SDCARD_INFO_FILE, FS_O_READ | FS_O_RDWR);
    if (rc < 0) {
        LOG_ERR("error opening file %d", rc);
        return -1;
    }
    rc = fs_seek(&read_file, 0, FS_SEEK_SET);
    if (rc < 0) {
        LOG_ERR("error seeking file %d", rc);
        return -1;
    }
    rc = fs_read(&read_file, &buf, 4);
    if (rc < 0) {
        LOG_ERR("error reading file %d", rc);
        return -1;
    }
    fs_close(&read_file);
    uint32_t *offset_ptr = (uint32_t *) buf;
    LOG_INF("get offset is %d", offset_ptr[0]);
    fs_close(&read_file);

    return offset_ptr[0];
}

void sd_off()
{
    //    gpio_pin_set_dt(&sd_en_gpio_pin, 0);
    sd_enabled = false;
}

void sd_on()
{
    //    gpio_pin_set_dt(&sd_en_gpio_pin, 1);
    sd_enabled = true;
}

bool is_sd_on()
{
    return sd_enabled;
}

int save_chunk_counters(uint32_t start_counter, uint32_t current_counter)
{
    uint8_t buf[8] = {
        start_counter & 0xFF,
        (start_counter >> 8) & 0xFF,
        (start_counter >> 16) & 0xFF,
        (start_counter >> 24) & 0xFF,
        current_counter & 0xFF,
        (current_counter >> 8) & 0xFF,
        (current_counter >> 16) & 0xFF,
        (current_counter >> 24) & 0xFF,
    };

    struct fs_file_t write_file;
    fs_file_t_init(&write_file);
    int res = fs_open(&write_file, SDCARD_CHUNK_COUNTER_FILE, FS_O_WRITE | FS_O_CREATE);
    if (res < 0) 
    {
        LOG_ERR("error opening chunk counter file %d", res);
        return res;
    }
    res = fs_seek(&write_file, 0, FS_SEEK_SET);
    if (res < 0) {
        LOG_ERR("error seeking chunk counter file %d", res);
        fs_close(&write_file);
        return res;
    }
    res = fs_write(&write_file, buf, sizeof(buf));
    if (res < 0)
    {
        LOG_ERR("error writing chunk counter file %d", res);
        fs_close(&write_file);
        return res;
    }
    if (res != sizeof(buf)) {
        LOG_ERR("partial write to chunk counter file: %d", res);
        fs_close(&write_file);
        return -EIO;
    }
    res = fs_truncate(&write_file, sizeof(buf));
    if (res < 0) {
        LOG_WRN("failed to truncate chunk counter file: %d", res);
        // continue; data already written, truncate failure likely harmless
    }
    fs_close(&write_file);
    return 0;
}

int get_chunk_counters(uint32_t *start_counter, uint32_t *current_counter)
{
    if (start_counter == NULL || current_counter == NULL) {
        return -EINVAL;
    }
    
    uint8_t buf[8];
    struct fs_file_t read_file;
    fs_file_t_init(&read_file);
    int rc = fs_open(&read_file, SDCARD_CHUNK_COUNTER_FILE, FS_O_READ);
    if (rc < 0)
    {
        // File doesn't exist, start with counter 0
        LOG_INF("chunk counter file doesn't exist, starting with 0");
        *start_counter = 0;
        *current_counter = 0;
        return 0;
    }
    
    rc = fs_read(&read_file, buf, sizeof(buf));
    fs_close(&read_file);
    
    if (rc < 0)
    {
        LOG_ERR("error reading chunk counter file %d", rc);
        return rc; // Return the actual error code
    }
    
    if (rc != sizeof(buf)) {
        LOG_ERR("incomplete read of chunk counters, got %d bytes", rc);
        return -EIO;
    }
    
    uint32_t *counter_ptr = (uint32_t*)buf;
    *start_counter = counter_ptr[0];
    *current_counter = counter_ptr[1];
    if (*current_counter < *start_counter) {
        LOG_WRN("Chunk counters corrupted (current < start), resetting to start value");
        *current_counter = *start_counter;
    }
    LOG_INF("loaded chunk counters: start=%d current=%d", *start_counter, *current_counter);
    return 0;
}

char* generate_chunk_audio_filename(void)
{
    // Increment and save the chunk counter for unique filenames across reboots
    chunk_current_counter++;
    if (chunk_start_counter == 0 || chunk_start_counter > chunk_current_counter) {
        chunk_start_counter = chunk_current_counter;
    }
    int ret = save_chunk_counters(chunk_start_counter, chunk_current_counter);
    if (ret < 0) {
        LOG_ERR("Failed to save chunk counter: %d", ret);
        // Continue anyway - we can still generate filename with current counter
    }
    
    char *filename = k_malloc(CHUNK_FILENAME_MAX_LENGTH);
    if (filename == NULL) {
        LOG_ERR("Failed to allocate memory for chunk filename");
        return NULL;
    }
    
    // Format: audio/chunk_NNNNN.bin
    int len = snprintf(filename, CHUNK_FILENAME_MAX_LENGTH, CHUNK_FILENAME_FORMAT,
                      (int)chunk_current_counter);
    
    if (len >= CHUNK_FILENAME_MAX_LENGTH || len < 0) {
        LOG_ERR("Filename too long or formatting error");
        k_free(filename);
        return NULL;
    }
    
    LOG_DBG("Generated chunk filename: %s", filename);
    return filename;
}

void get_chunk_counter_snapshot(uint32_t *start_counter, uint32_t *current_counter)
{
    if (start_counter == NULL || current_counter == NULL) {
        return;
    }

    if (!chunking_enabled) {
        *start_counter = 0;
        *current_counter = 0;
        return;
    }

    *start_counter = chunk_start_counter;
    *current_counter = chunk_current_counter;
}

int initialize_chunk_file(void)
{
    // Safety check - ensure chunking is enabled and SD is properly initialized
    if (!chunking_enabled) {
        LOG_ERR("Cannot initialize chunk - chunking disabled");
        return SDCARD_ERR_CHUNKING_DISABLED;
    }
    
    if (!sd_enabled) {
        LOG_ERR("Cannot initialize chunk - SD not enabled");
        return SDCARD_ERR_SD_NOT_ENABLED;
    }
    
    char *filename = generate_chunk_audio_filename();
    if (filename == NULL) {
        LOG_ERR("Failed to generate chunk filename - out of memory");
        return SDCARD_ERR_FILENAME_GENERATION;
    }
    
    // Copy to current chunk filename buffer
    strncpy(current_chunk_filename, filename, sizeof(current_chunk_filename) - 1);
    current_chunk_filename[sizeof(current_chunk_filename) - 1] = '\0';
    
    // Create the file
    int ret = create_file(filename);
    k_free(filename);
    
    if (ret == 0) {
        // Update write buffer to point to new file
        int len = snprintf(write_buffer, sizeof(write_buffer), "%s%s", disk_mount_pt, current_chunk_filename);
        if (len >= sizeof(write_buffer)) {
            LOG_ERR("Write buffer path too long, truncated");
            // Reset chunk state on path error
            chunk_active = false;
            memset(current_chunk_filename, 0, sizeof(current_chunk_filename));
            return SDCARD_ERR_FILENAME_GENERATION;
        }
        atomic_set(&chunk_cycle_counter, 0);     // Thread-safe: Reset cycle counter for new chunk
        chunk_active = true;
        atomic_set(&should_rotate_flag, 0);      // Thread-safe: Reset rotation flag for new chunk
        LOG_INF("NEW AUDIO CHUNK CREATED: %s", current_chunk_filename);
        LOG_DBG("File path: %s", write_buffer);
        LOG_DBG("Chunk will rotate in %d cycles (%d seconds)", CHUNK_DURATION_CYCLES, CHUNK_DURATION_CYCLES / 2);
        LOG_DBG("Chunk start counter: %d", chunk_start_counter);
        LOG_DBG("Chunk current counter: %d", chunk_current_counter);
        LOG_DBG("Chunking state: active=%d enabled=%d sd_enabled=%d boot_complete=%d", 
                chunk_active, chunking_enabled, sd_enabled, system_boot_complete);
    } else {
        LOG_ERR("Failed to create chunk file: %d", ret);
        // Reset chunk state on failure
        chunk_active = false;
        memset(current_chunk_filename, 0, sizeof(current_chunk_filename));
    }
    
    return ret;
}

bool should_rotate_chunk(void)
{
    // Safety check - if chunking disabled, SD not enabled, or system still booting
    if (!chunking_enabled || !sd_enabled || !system_boot_complete) {
        return false;
    }
    
    if (!chunk_active) {
        return true; // No active chunk, should start one
    }
    
    // Thread-safe: Atomic read of the rotation flag
    return atomic_get(&should_rotate_flag) != 0;
}

void check_chunk_rotation_timing(void)
{
    // This function should be called every 500ms from main loop
    // Only check timing if chunking is enabled and chunk is active
    if (!chunking_enabled || !sd_enabled || !system_boot_complete || !chunk_active) {
        atomic_set(&should_rotate_flag, 0);  // Clear flag
        atomic_set(&chunk_cycle_counter, 0); // Reset counter when not active
        return;
    }
    
    // Thread-safe: Atomic increment of the cycle counter
    uint32_t current_cycles = atomic_inc(&chunk_cycle_counter);
    
    // Set the flag if we've reached the target number of cycles
    if (current_cycles >= CHUNK_DURATION_CYCLES) {
        atomic_set(&should_rotate_flag, 1);
    }
}

int start_new_chunk(void)
{
    if (chunk_active) {
        uint32_t cycles = atomic_get(&chunk_cycle_counter);  // Thread-safe read
        LOG_INF("FINALIZING CHUNK: %s", current_chunk_filename);
        LOG_INF("Duration: %d cycles (%d seconds)", cycles, cycles / 2);
        // Current chunk is automatically finalized when we stop writing to it
    } else {
        // New chunk session starting; initialize start counter only if not already set
        if (chunk_start_counter == 0 && chunk_current_counter == 0) {
            chunk_start_counter = 1;
            int ret = save_chunk_counters(chunk_start_counter, chunk_current_counter);
            if (ret < 0) {
                LOG_ERR("Failed to initialize chunk counters for new session: %d", ret);
                return ret;
            }
        }
    }

    return initialize_chunk_file();
}

static int chunk_id_to_path(uint32_t chunk_id, char *out_path, size_t path_len)
{
    if (chunk_id == 0 || out_path == NULL) {
        return -EINVAL;
    }

    int len = snprintf(out_path,
                       path_len,
                       "%s" CHUNK_FILENAME_FORMAT,
                       SDCARD_MOUNT_POINT,
                       (int)chunk_id);

    LOG_DBG("chunk_id_to_path: chunk_id=%d path=%s len=%d", chunk_id, out_path, len);
    if (len < 0 || (size_t)len >= path_len) {
        return -ENAMETOOLONG;
    }
    return 0;
}

int stream_chunk_file(uint32_t chunk_id, uint32_t *out_size)
{
    if (!chunking_enabled) {
        return SDCARD_ERR_CHUNKING_DISABLED;
    }

    // Validate chunk_id is within valid range
    if (chunk_start_counter == 0 && chunk_current_counter == 0) {
        LOG_WRN("No chunks exist to stream (chunk_id=%u)", chunk_id);
        return -ENOENT;
    }

    if (chunk_id < chunk_start_counter || chunk_id > chunk_current_counter) {
        LOG_WRN("Chunk ID %u out of valid range [%u, %u]", 
                chunk_id, chunk_start_counter, chunk_current_counter);
        return -EINVAL;
    }

    int ret = chunk_id_to_path(chunk_id, read_buffer, sizeof(read_buffer));
    if (ret) {
        LOG_ERR("chunk_id_to_path failed for %u: %d", chunk_id, ret);
        return ret;
    }

    LOG_DBG("Streaming chunk %u from path: %s", chunk_id, read_buffer);
    struct fs_dirent entry;
    ret = fs_stat(read_buffer, &entry);
    if (ret) {
        LOG_ERR("chunk %u not found", chunk_id);
        return -ENOENT;
    }

    if (out_size != NULL) {
        *out_size = (uint32_t)entry.size;
        LOG_DBG("chunk %u size: %u", chunk_id, *out_size);
    }

    return 0;
}

int delete_chunk_file(uint32_t chunk_id)
{
    if (!chunking_enabled) {
        return SDCARD_ERR_CHUNKING_DISABLED;
    }

    // Validate chunk_id is within valid range
    if (chunk_start_counter == 0 && chunk_current_counter == 0) {
        LOG_WRN("No chunks exist to delete (chunk_id=%u)", chunk_id);
        return -ENOENT;
    }

    if (chunk_id < chunk_start_counter || chunk_id > chunk_current_counter) {
        LOG_WRN("Chunk ID %u out of valid range [%u, %u]", 
                chunk_id, chunk_start_counter, chunk_current_counter);
        return -EINVAL;
    }

    char path[MAX_PATH_LENGTH];
    int ret = chunk_id_to_path(chunk_id, path, sizeof(path));
    if (ret) {
        return ret;
    }

    ret = fs_unlink(path);
    if (ret) {
        if (ret == -EIO) {
            LOG_WRN("fs_unlink returned -EIO for %s, treating as success", path);
        } else {
            LOG_ERR("Failed to delete chunk %u: %d", chunk_id, ret);
            return ret;
        }
    }

    if (chunk_id == chunk_start_counter) {
        uint32_t start = chunk_start_counter + 1;
        uint32_t current = chunk_current_counter;
        char path_check[MAX_PATH_LENGTH];
        struct fs_dirent entry;
        bool found = false;

        for (uint32_t id = start; id <= current; ++id) {
            if (chunk_id_to_path(id, path_check, sizeof(path_check)) == 0 && fs_stat(path_check, &entry) == 0) {
                chunk_start_counter = id;
                found = true;
                break;
            }
        }

        if (!found) {
            chunk_start_counter = chunk_current_counter = 0;
        }
    } else if (chunk_id == chunk_current_counter) {
        char path_check[MAX_PATH_LENGTH];
        struct fs_dirent entry;
        bool found = false;

        for (uint32_t id = chunk_current_counter - 1; id >= chunk_start_counter && id > 0; --id) {
            if (chunk_id_to_path(id, path_check, sizeof(path_check)) == 0 && fs_stat(path_check, &entry) == 0) {
                chunk_current_counter = id;
                found = true;
                break;
            }
        }

        if (!found) {
            chunk_start_counter = chunk_current_counter = 0;
        }
    }

    ret = save_chunk_counters(chunk_start_counter, chunk_current_counter);
    if (ret < 0) {
        LOG_ERR("Failed to persist chunk counters after delete: %d", ret);
        return ret;
    }

    return 0;
}

void set_system_boot_complete(void)
{
    system_boot_complete = true;
    LOG_INF("System boot marked as complete - chunking enabled");
}
