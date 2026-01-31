#include "lib/core/sd_card.h"
#include "rtc.h"
#include <ff.h>
#include <zephyr/fs/fs.h>
#include <string.h>
#include <stdlib.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/fs/fs.h>
#include <zephyr/fs/fs_sys.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/check.h>

LOG_MODULE_REGISTER(sd_card, CONFIG_LOG_DEFAULT_LEVEL);

#define DISK_DRIVE_NAME "SD"        // Disk drive name
#define DISK_MOUNT_PT "/SD:"        // Mount point path
#define SD_REQ_QUEUE_MSGS  25       // Number of messages in the SD request queue
#define SD_FSYNC_THRESHOLD 20000    // Threshold in bytes to trigger fsync
#define WRITE_BATCH_COUNT 10         // Number of writes to batch before writing to SD card
#define ERROR_THRESHOLD 5           // Maximum allowed write errors before taking action

// batch write buffer
static uint8_t write_batch_buffer[WRITE_BATCH_COUNT * MAX_WRITE_SIZE];
static size_t write_batch_offset = 0;
static int write_batch_counter = 0;
static uint8_t writing_error_counter = 0;

static FATFS fat_fs;

static struct fs_mount_t mp = {
    .type = FS_FATFS,
    .fs_data = &fat_fs,
    .flags = FS_MOUNT_FLAG_NO_FORMAT | FS_MOUNT_FLAG_USE_DISK_ACCESS,
    .storage_dev = (void *) DISK_DRIVE_NAME,
    .mnt_point = DISK_MOUNT_PT,
};

#define FILE_DATA_DIR "/SD:/audio"
#define FILE_INFO_PATH "/SD:/info.txt"

static struct fs_file_t fil_data;
static struct fs_file_t fil_info;

static bool is_mounted = false;
static bool sd_enabled = false;
static uint32_t current_file_size = 0;
static size_t bytes_since_sync = 0;

// Current writing file info
static char current_filename[MAX_FILENAME_LEN] = {0};
static char current_file_path[64] = {0};
static int64_t current_file_created_uptime_ms = 0;  // Uptime when file was created
static bool current_file_needs_rename = false;      // True if file was created without valid RTC
// BLE connection tracking for file rotation
static bool ble_connected = false;
static int64_t ble_connect_time_ms = 0;

// Offset info (oldest file + offset in that file)
static sd_offset_info_t current_offset_info = {0};

// Get the device pointer for the SDHC SPI slot from the device tree
static const struct device *const sd_dev = DEVICE_DT_GET(DT_NODELABEL(sdhc0));
static const struct gpio_dt_spec sd_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

K_MSGQ_DEFINE(sd_msgq, sizeof(sd_req_t), SD_REQ_QUEUE_MSGS, 4);

void sd_worker_thread(void);

/* Forward declarations for internal functions */
static int create_audio_file_with_timestamp(void);
static int flush_batch_buffer(void);
static void build_file_path(const char *filename, char *path, size_t path_size);

static int sd_enable_power(bool enable)
{
    int ret;
    gpio_pin_configure_dt(&sd_en, GPIO_OUTPUT);
    const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi3));
    if (enable) {
        ret = gpio_pin_set_dt(&sd_en, 1);

        if (device_is_ready(spi_dev)) {
            /* Resume SPI and SD devices */
            pm_device_action_run(spi_dev, PM_DEVICE_ACTION_RESUME);
            pm_device_action_run(sd_dev, PM_DEVICE_ACTION_RESUME);
        }
        sd_enabled = true;
    } else {
        if (device_is_ready(spi_dev)) {
            /* Suspend SPI and SD devices to save power */
            pm_device_action_run(sd_dev, PM_DEVICE_ACTION_SUSPEND);
            pm_device_action_run(spi_dev, PM_DEVICE_ACTION_SUSPEND);
        }

        /* Zephyr didn't handle CS pin in suspend, we handle it manually */
        gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 11, GPIO_DISCONNECTED);
        ret = gpio_pin_set_dt(&sd_en, 0);
        sd_enabled = false;
    }
    return ret;
}

static int sd_unmount()
{
    // Flush any remaining batch data before unmounting
    if (write_batch_offset > 0) {
        flush_batch_buffer();
    }
    
    // Ensure files are closed before unmounting
    fs_close(&fil_data);
    fs_close(&fil_info);
    int ret;
    ret = fs_unmount(&mp);
    if (ret) {
        LOG_INF("Disk unmounted error (%d) .", ret);
        return ret;
    }

    LOG_INF("Disk unmounted.");
    is_mounted = false;
    sd_enable_power(false);
    return 0;
}

static int sd_mount()
{
    int ret;
    do {
        static const char *disk_pdrv = DISK_DRIVE_NAME;
        uint64_t memory_size_mb;
        uint32_t block_count;
        uint32_t block_size;

        ret = sd_enable_power(true);
        if (ret < 0) {
            LOG_ERR("Failed to power on SD card (%d)", ret);
            return ret;
        }

        int init_ret;
        init_ret = disk_access_ioctl(disk_pdrv, DISK_IOCTL_CTRL_INIT, NULL);
        if (init_ret != 0) {
            LOG_ERR("Storage init ERROR! (%d)", init_ret);
            break;
        }

        if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_GET_SECTOR_COUNT, &block_count)) {
            LOG_ERR("Unable to get sector count");
            break;
        }
        LOG_INF("Block count %u", block_count);

        if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_GET_SECTOR_SIZE, &block_size)) {
            LOG_ERR("Unable to get sector size");
            break;
        }
        LOG_INF("Sector size %u", block_size);

        memory_size_mb = (uint64_t) block_count * block_size;
        LOG_INF("Memory Size(MB) %u", (uint32_t) (memory_size_mb >> 20));

        if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_CTRL_DEINIT, NULL) != 0) {
            LOG_ERR("Storage deinit ERROR!");
            break;
        }
    } while (0);
    mp.mnt_point = DISK_MOUNT_PT;

    if (is_mounted) {
        LOG_INF("Disk already mounted.");
        return 0;
    }

    if (fs_mount(&mp)) {
        LOG_INF("File system not found, creating file system...");
        ret = fs_mkfs(FS_FATFS, (uintptr_t) mp.storage_dev, NULL, 0);
        if (ret != 0) {
            LOG_ERR("Error formatting filesystem [%d]", ret);
            sd_enable_power(false);
            return ret;
        }

        ret = fs_mount(&mp);
        if (ret) {
            LOG_INF("Error mounting disk %d.", ret);
            sd_enable_power(false);
            return ret;
        }
    }

    LOG_INF("Disk mounted.");
    is_mounted = true;

    return ret;
}

/* Build full file path from filename */
static void build_file_path(const char *filename, char *path, size_t path_size)
{
    snprintf(path, path_size, "%s/%s", FILE_DATA_DIR, filename);
}

/* Print all audio files with their sizes at boot */
static void print_audio_files_at_boot(void)
{
    struct fs_dir_t dir;
    struct fs_dirent entry;
    char file_path[64];
    uint32_t file_count = 0;
    uint64_t total_size = 0;
    int all_entries = 0;
    
    fs_dir_t_init(&dir);
    int ret = fs_opendir(&dir, FILE_DATA_DIR);
    if (ret < 0) {
        LOG_INF("[SD_BOOT] No audio directory found (err=%d)", ret);
        return;
    }
    
    LOG_INF("========== AUDIO FILES ON SD CARD ==========");
    
    while (1) {
        ret = fs_readdir(&dir, &entry);
        if (ret < 0) {
            LOG_ERR("[SD_BOOT] readdir error: %d", ret);
            break;
        }
        if (entry.name[0] == '\0') {
            break;
        }
        
        all_entries++;
        
        if (entry.type == FS_DIR_ENTRY_FILE) {
            // Check if it's a .txt file
            char *dot = strrchr(entry.name, '.');
            if (dot && strcmp(dot, ".TXT") == 0) {
                // FAT returns uppercase extension
                build_file_path(entry.name, file_path, sizeof(file_path));
                struct fs_dirent file_stat;
                if (fs_stat(file_path, &file_stat) == 0) {
                    LOG_INF("  [%u] %s - %u bytes", file_count + 1, entry.name, (unsigned)file_stat.size);
                    total_size += file_stat.size;
                    file_count++;
                }
            } else if (dot && strcmp(dot, ".txt") == 0) {
                // Also check lowercase
                build_file_path(entry.name, file_path, sizeof(file_path));
                struct fs_dirent file_stat;
                if (fs_stat(file_path, &file_stat) == 0) {
                    LOG_INF("  [%u] %s - %u bytes", file_count + 1, entry.name, (unsigned)file_stat.size);
                    total_size += file_stat.size;
                    file_count++;
                }
            }
        }
    }
    
    fs_closedir(&dir);
    
    LOG_INF("[SD_BOOT] Total entries scanned: %d", all_entries);
    
    if (file_count == 0) {
        LOG_INF("  (No audio files found)");
    } else {
        LOG_INF("--------------------------------------------");
        LOG_INF("  Total: %u files, %u bytes (%.2f MB)", 
                file_count, (unsigned)total_size, (float)total_size / (1024.0f * 1024.0f));
    }
    LOG_INF("=============================================");
}

/* Time threshold for continuing to write to existing file (30 minutes in seconds) */
#define FILE_CONTINUE_THRESHOLD_SEC (30 * 60)

/**
 * @brief Find the latest audio file and check if we can continue writing to it
 * 
 * On boot, check if the latest file's timestamp is within 30 minutes of current time.
 * If yes, open that file for appending instead of creating a new one.
 * 
 * @return 0 if successfully opened existing file, -1 if should create new file
 */
static int try_continue_latest_file(void)
{
    struct fs_dir_t dir;
    struct fs_dirent entry;
    char latest_filename[MAX_FILENAME_LEN] = {0};
    uint32_t latest_timestamp = 0;
    
    uint32_t current_time = get_utc_time();
    if (current_time == 0 || current_time < 1700000000) {
        LOG_INF("[SD_BOOT] RTC not valid, cannot check file age - will create new file");
        return -1;
    }
    
    fs_dir_t_init(&dir);
    int ret = fs_opendir(&dir, FILE_DATA_DIR);
    if (ret < 0) {
        LOG_INF("[SD_BOOT] No audio directory, will create new file");
        return -1;
    }
    
    // Find the latest file (highest timestamp)
    while (1) {
        ret = fs_readdir(&dir, &entry);
        if (ret < 0 || entry.name[0] == '\0') {
            break;
        }
        
        if (entry.type == FS_DIR_ENTRY_FILE) {
            char *dot = strrchr(entry.name, '.');
            if (dot && (strcmp(dot, ".TXT") == 0 || strcmp(dot, ".txt") == 0)) {
                // Parse hex timestamp from filename
                uint32_t file_timestamp = (uint32_t)strtoul(entry.name, NULL, 16);
                if (file_timestamp > latest_timestamp) {
                    latest_timestamp = file_timestamp;
                    strncpy(latest_filename, entry.name, sizeof(latest_filename) - 1);
                }
            }
        }
    }
    fs_closedir(&dir);
    
    if (latest_filename[0] == '\0') {
        LOG_INF("[SD_BOOT] No audio files found, will create new file");
        return -1;
    }
    
    // Check if the latest file is within 30 minutes of current time
    int32_t time_diff = (int32_t)(current_time - latest_timestamp);
    LOG_INF("[SD_BOOT] Latest file: %s (timestamp=%u, current=%u, diff=%d sec)", 
            latest_filename, latest_timestamp, current_time, time_diff);
    
    if (time_diff < 0) {
        // File is in the future? Shouldn't happen, but handle it
        LOG_WRN("[SD_BOOT] Latest file timestamp is in the future, will create new file");
        return -1;
    }
    
    if (time_diff > FILE_CONTINUE_THRESHOLD_SEC) {
        LOG_INF("[SD_BOOT] Latest file is too old (%d sec > %d sec), will create new file",
                time_diff, FILE_CONTINUE_THRESHOLD_SEC);
        return -1;
    }
    
    // Open the existing file for appending
    strncpy(current_filename, latest_filename, sizeof(current_filename) - 1);
    build_file_path(current_filename, current_file_path, sizeof(current_file_path));
    
    fs_file_t_init(&fil_data);
    ret = fs_open(&fil_data, current_file_path, FS_O_RDWR | FS_O_APPEND);
    if (ret < 0) {
        LOG_ERR("[SD_BOOT] Failed to open existing file %s: %d", current_file_path, ret);
        current_filename[0] = '\0';
        current_file_path[0] = '\0';
        return -1;
    }
    
    // Get current file size
    ret = fs_seek(&fil_data, 0, FS_SEEK_END);
    if (ret >= 0) {
        current_file_size = fs_tell(&fil_data);
    } else {
        current_file_size = 0;
    }
    
    bytes_since_sync = 0;
    write_batch_offset = 0;
    write_batch_counter = 0;
    current_file_created_uptime_ms = k_uptime_get();
    current_file_needs_rename = false;  // File already has valid timestamp
    
    LOG_INF("[SD_BOOT] Continuing to write to existing file: %s (size=%u, age=%d sec)",
            current_filename, current_file_size, time_diff);
    
    return 0;
}

/* Create a new audio file with current UTC timestamp as filename */
static int create_audio_file_with_timestamp(void)
{
    /* Check if RTC time is valid/synced */
    if (!rtc_is_valid()) {
        LOG_DBG("RTC not synced yet, waiting for time sync");
        return -EAGAIN;  /* Return error to indicate time not synced */
    }
    
    uint32_t timestamp = get_utc_time();
    if (timestamp == 0 || timestamp < 1700000000) {  /* Before ~2023 */
        LOG_DBG("Invalid timestamp %u, waiting for time sync", timestamp);
        return -EAGAIN;
    }
    
    // Close current file if open
    if (current_filename[0] != '\0') {
        // Flush any remaining batch data
        if (write_batch_offset > 0) {
            flush_batch_buffer();
        }
        fs_close(&fil_data);
    }
    
    // Ensure audio directory exists
    struct fs_dirent dir_stat;
    int stat_res = fs_stat(FILE_DATA_DIR, &dir_stat);
    if (stat_res < 0) {
        LOG_INF("Audio directory does not exist, creating: %s", FILE_DATA_DIR);
        int mk_res = fs_mkdir(FILE_DATA_DIR);
        if (mk_res < 0 && mk_res != -EEXIST) {
            LOG_ERR("Failed to create audio directory: %d", mk_res);
            return mk_res;
        }
    }
    
    // Generate new filename based on timestamp (hex format to fit 8.3 FAT filename)
    // Hex timestamp is max 8 chars, fits FAT 8.3 limit
    snprintf(current_filename, sizeof(current_filename), "%08X.txt", timestamp);
    build_file_path(current_filename, current_file_path, sizeof(current_file_path));
    
    LOG_INF("Creating new audio file: %s", current_file_path);
    
    // Create and open the new file
    fs_file_t_init(&fil_data);
    int ret = fs_open(&fil_data, current_file_path, FS_O_CREATE | FS_O_RDWR);
    if (ret < 0) {
        LOG_ERR("Failed to create audio file %s: %d", current_file_path, ret);
        current_filename[0] = '\0';
        current_file_path[0] = '\0';
        return ret;
    }
    
    current_file_size = 0;
    bytes_since_sync = 0;
    write_batch_offset = 0;
    write_batch_counter = 0;
    current_file_created_uptime_ms = k_uptime_get();
    
    // Check if RTC was valid when creating file
    uint32_t rtc_time = get_utc_time();
    current_file_needs_rename = (rtc_time == 0 || rtc_time < 1700000000);  // Before ~2023
    
    LOG_INF("Audio file created: %s (needs_rename=%d)", current_filename, current_file_needs_rename);
    return 0;
}

/* Flush the batch buffer to SD card */
static int flush_batch_buffer(void)
{
    if (write_batch_offset == 0) {
        return 0;
    }
    
    int res = fs_seek(&fil_data, 0, FS_SEEK_END);
    if (res < 0) {
        LOG_ERR("seek end before write failed: %d", res);
        return res;
    }
    
    ssize_t bw = fs_write(&fil_data, write_batch_buffer, write_batch_offset);
    if (bw < 0 || (size_t)bw != write_batch_offset) {
        writing_error_counter++;
        LOG_ERR("batch write error bw=%d wanted=%u", (int)bw, (unsigned)write_batch_offset);
        
        if (bw > 0) {
            LOG_INF("Attempting to truncate to correct packet position");
            uint32_t truncate_offset = current_file_size + bw - bw % MAX_WRITE_SIZE;
            int ret = fs_truncate(&fil_data, truncate_offset);
            if (ret < 0) {
                LOG_ERR("Failed to truncate to next packet position: %d", ret);
            } else {
                LOG_INF("Shifted file pointer to correct packet position: %u", truncate_offset);
                current_file_size = truncate_offset;
            }
        }
        
        if (writing_error_counter >= ERROR_THRESHOLD) {
            LOG_ERR("Too many write errors (%d). Re-opening file.", writing_error_counter);
            fs_close(&fil_data);
            fs_file_t_init(&fil_data);
            int reopen_res = fs_open(&fil_data, current_file_path, FS_O_CREATE | FS_O_RDWR);
            if (reopen_res == 0) {
                writing_error_counter = 0;
                fs_seek(&fil_data, 0, FS_SEEK_END);
            } else {
                LOG_ERR("Re-open file failed: %d", reopen_res);
            }
        }
        
        write_batch_offset = 0;
        write_batch_counter = 0;
        return -EIO;
    }
    
    bytes_since_sync += bw;
    current_file_size += bw;
    write_batch_offset = 0;
    write_batch_counter = 0;
    
    return 0;
}

/* Check if we need to rotate to a new file due to BLE connection time */
static bool should_rotate_file(void)
{
    if (!ble_connected) {
        return false;
    }
    
    int64_t now_ms = k_uptime_get();
    int64_t connection_duration_ms = now_ms - ble_connect_time_ms;
    
    return (connection_duration_ms >= FILE_ROTATION_INTERVAL_MS);
}

/* Compare function for sorting filenames (hex timestamps) */
static int compare_filenames(const void *a, const void *b)
{
    const char *fa = (const char *)a;
    const char *fb = (const char *)b;
    
    // Extract hex timestamps from filenames (format: XXXXXXXX.txt)
    uint32_t ts_a = (uint32_t)strtoul(fa, NULL, 16);
    uint32_t ts_b = (uint32_t)strtoul(fb, NULL, 16);
    
    if (ts_a < ts_b) return -1;
    if (ts_a > ts_b) return 1;
    return 0;
}

/**
 * @brief Update current audio filename after receiving time sync from BLE
 * 
 * When device boots without RTC time, it creates file with uptime-based name.
 * After receiving real timestamp from BLE, calculate correct timestamp:
 * correct_timestamp = received_timestamp - (current_uptime - file_created_uptime) / 1000
 */
void sd_update_filename_after_timesync(uint32_t synced_utc_time)
{
    if (!current_file_needs_rename) {
        LOG_DBG("File doesn't need renaming");
        return;
    }
    
    if (current_filename[0] == '\0') {
        LOG_WRN("No current file to rename");
        return;
    }
    
    if (!is_mounted) {
        LOG_WRN("SD card not mounted, cannot rename");
        return;
    }
    
    // Calculate the correct timestamp for when file was created
    int64_t now_ms = k_uptime_get();
    int64_t elapsed_since_file_created_ms = now_ms - current_file_created_uptime_ms;
    uint32_t correct_timestamp = synced_utc_time - (uint32_t)(elapsed_since_file_created_ms / 1000);
    
    // Generate new filename
    char new_filename[MAX_FILENAME_LEN];
    char new_file_path[64];
    snprintf(new_filename, sizeof(new_filename), "%08X.TXT", correct_timestamp);
    build_file_path(new_filename, new_file_path, sizeof(new_file_path));
    
    LOG_INF("Renaming audio file: %s -> %s (synced_time=%u, elapsed=%lldms)", 
            current_filename, new_filename, synced_utc_time, elapsed_since_file_created_ms);
    
    // Flush any pending data before rename
    if (write_batch_offset > 0) {
        flush_batch_buffer();
    }
    fs_sync(&fil_data);
    
    // Close the file before renaming
    fs_close(&fil_data);
    
    // Rename the file
    int ret = fs_rename(current_file_path, new_file_path);
    if (ret < 0) {
        LOG_ERR("Failed to rename file: %d", ret);
        // Reopen the old file
        fs_file_t_init(&fil_data);
        fs_open(&fil_data, current_file_path, FS_O_RDWR | FS_O_APPEND);
        return;
    }
    
    // Update current filename and path
    strncpy(current_filename, new_filename, sizeof(current_filename) - 1);
    strncpy(current_file_path, new_file_path, sizeof(current_file_path) - 1);
    current_file_needs_rename = false;
    
    // Reopen the renamed file
    fs_file_t_init(&fil_data);
    ret = fs_open(&fil_data, current_file_path, FS_O_RDWR | FS_O_APPEND);
    if (ret < 0) {
        LOG_ERR("Failed to reopen renamed file: %d", ret);
        return;
    }
    
    // Seek to end for appending
    fs_seek(&fil_data, 0, FS_SEEK_END);
    
    LOG_INF("File renamed successfully to: %s", current_filename);
}

#define SD_WORKER_STACK_SIZE 4096
#define SD_WORKER_PRIORITY 7
K_THREAD_STACK_DEFINE(sd_worker_stack, SD_WORKER_STACK_SIZE);
static struct k_thread sd_worker_thread_data;
static k_tid_t sd_worker_tid = NULL;

int app_sd_init(void)
{
    if (!sd_worker_tid) {
        sd_worker_tid = k_thread_create(&sd_worker_thread_data, sd_worker_stack, SD_WORKER_STACK_SIZE,
                                        (k_thread_entry_t)sd_worker_thread, NULL, NULL, NULL,
                                        SD_WORKER_PRIORITY, 0, K_NO_WAIT);
        k_thread_name_set(sd_worker_tid, "sd_worker");
    }
    return 0;
}

uint32_t get_file_size(void)
{
    return current_file_size;
}

int get_current_filename(char *buf, size_t buf_size)
{
    if (buf == NULL || buf_size < MAX_FILENAME_LEN) {
        return -EINVAL;
    }
    strncpy(buf, current_filename, buf_size - 1);
    buf[buf_size - 1] = '\0';
    return 0;
}

void sd_notify_ble_state(bool connected)
{
    if (connected && !ble_connected) {
        // BLE just connected
        ble_connect_time_ms = k_uptime_get();
        LOG_INF("BLE connected, tracking connection time for file rotation");
    } else if (!connected && ble_connected) {
        // BLE just disconnected - reset tracking
        LOG_INF("BLE disconnected");
    }
    ble_connected = connected;
}

int read_audio_data(const char *filename, uint8_t *buf, int amount, int offset)
{
    struct read_resp resp;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_READ_DATA;
    strncpy(req.u.read.filename, filename, MAX_FILENAME_LEN - 1);
    req.u.read.out_buf = buf;
    req.u.read.length = amount;
    req.u.read.offset = offset;
    req.u.read.resp = &resp;

    int ret = k_msgq_put(&sd_msgq, &req, K_MSEC(100));
    if (ret) {
        LOG_ERR("Failed to queue read_audio_data request: %d", ret);
        return ret;
    }

    if (k_sem_take(&resp.sem, K_MSEC(5000)) != 0) {
        LOG_ERR("Timeout waiting for read_audio_data response");
        return -1;
    }
    if (resp.res) {
        LOG_ERR("Failed to read audio data: %d", resp.res);
        return -1;
    }
    return resp.read_bytes;
}


uint32_t write_to_file(uint8_t *data, uint32_t length)
{
    // If RTC is not synced, silently ignore the data
    // We can't create proper timestamped files without valid time
    if (!rtc_is_valid()) {
        return length;  // Pretend success, data is discarded
    }

    sd_req_t req = {0};
    req.type = REQ_WRITE_DATA;
    memcpy(req.u.write.buf, data, length);
    req.u.write.len = length;

    int ret = k_msgq_put(&sd_msgq, &req, K_MSEC(100));
    if (ret) {
        LOG_ERR("Failed to queue write_to_file request: %d", ret);
        return 0;
    }

    return length;
}

int clear_audio_directory(void)
{
    struct read_resp resp;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_CLEAR_AUDIO_DIR;
    req.u.clear_dir.resp = &resp;

    int ret = k_msgq_put(&sd_msgq, &req, K_MSEC(100));
    if (ret) {
        LOG_ERR("Failed to queue clear_audio_directory request: %d", ret);
        return -1;
    }

    if (k_sem_take(&resp.sem, K_MSEC(5000)) != 0) {
        LOG_ERR("Timeout waiting for clear_audio_directory response");
        return -1;
    }

    if (resp.res) {
        LOG_ERR("Failed to clear audio directory: %d", resp.res);
        return -1;
    }

    return 0;
}

int save_offset(const char *filename, uint32_t offset)
{
    sd_req_t req = {0};
    req.type = REQ_SAVE_OFFSET;
    strncpy(req.u.info.offset_info.oldest_filename, filename, MAX_FILENAME_LEN - 1);
    req.u.info.offset_info.offset_in_file = offset;

    int ret = k_msgq_put(&sd_msgq, &req, K_MSEC(100));
    if (ret) {
        LOG_ERR("Failed to queue save_offset request: %d", ret);
        return -1;
    }
    return 0;
}

int get_offset(char *filename, uint32_t *offset)
{
    if (filename == NULL || offset == NULL) {
        return -EINVAL;
    }
    strncpy(filename, current_offset_info.oldest_filename, MAX_FILENAME_LEN - 1);
    filename[MAX_FILENAME_LEN - 1] = '\0';
    *offset = current_offset_info.offset_in_file;
    return 0;
}

int create_new_audio_file(void)
{
    struct read_resp resp;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_CREATE_NEW_FILE;
    req.u.create_file.resp = &resp;

    int ret = k_msgq_put(&sd_msgq, &req, K_MSEC(100));
    if (ret) {
        LOG_ERR("Failed to queue create_new_audio_file request: %d", ret);
        return -1;
    }

    if (k_sem_take(&resp.sem, K_MSEC(5000)) != 0) {
        LOG_ERR("Timeout waiting for create_new_audio_file response");
        return -1;
    }

    if (resp.res) {
        LOG_ERR("Failed to create new audio file: %d", resp.res);
        return -1;
    }

    // Reset BLE connection timer after creating new file
    if (ble_connected) {
        ble_connect_time_ms = k_uptime_get();
    }

    return 0;
}

int get_audio_file_stats(uint32_t *file_count, uint64_t *total_size)
{
    if (file_count == NULL || total_size == NULL) {
        return -EINVAL;
    }

    struct file_stats_resp resp;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_GET_FILE_STATS;
    req.u.file_stats.resp = &resp;

    int ret = k_msgq_put(&sd_msgq, &req, K_MSEC(100));
    if (ret) {
        LOG_ERR("Failed to queue get_audio_file_stats request: %d", ret);
        return -1;
    }

    if (k_sem_take(&resp.sem, K_MSEC(5000)) != 0) {
        LOG_ERR("Timeout waiting for get_audio_file_stats response");
        return -1;
    }

    if (resp.res) {
        LOG_ERR("Failed to get audio file stats: %d", resp.res);
        return -1;
    }

    *file_count = resp.file_count;
    *total_size = resp.total_size;
    return 0;
}

int get_audio_file_list(char filenames[][MAX_FILENAME_LEN], int max_files, int *count)
{
    if (filenames == NULL || count == NULL || max_files <= 0) {
        return -EINVAL;
    }

    if (!is_mounted) {
        return -ENODEV;
    }

    struct fs_dir_t dir;
    struct fs_dirent entry;
    int file_count = 0;
    
    fs_dir_t_init(&dir);
    int ret = fs_opendir(&dir, FILE_DATA_DIR);
    if (ret < 0) {
        LOG_ERR("Failed to open audio directory: %d", ret);
        return ret;
    }

    while (file_count < max_files) {
        ret = fs_readdir(&dir, &entry);
        if (ret < 0) {
            LOG_ERR("Failed to read directory: %d", ret);
            fs_closedir(&dir);
            return ret;
        }
        
        if (entry.name[0] == '\0') {
            // End of directory
            break;
        }
        
        if (entry.type == FS_DIR_ENTRY_FILE) {
            // Check if it's a .txt/.TXT file with numeric name (timestamp)
            char *dot = strrchr(entry.name, '.');
            if (dot && (strcmp(dot, ".txt") == 0 || strcmp(dot, ".TXT") == 0)) {
                strncpy(filenames[file_count], entry.name, MAX_FILENAME_LEN - 1);
                filenames[file_count][MAX_FILENAME_LEN - 1] = '\0';
                file_count++;
            }
        }
    }

    fs_closedir(&dir);
    
    // Sort files by timestamp (oldest first)
    if (file_count > 1) {
        qsort(filenames, file_count, MAX_FILENAME_LEN, compare_filenames);
    }
    
    *count = file_count;
    return 0;
}

int app_sd_off(void)
{
    if (is_mounted) {
        sd_unmount();
    } else {
        sd_enable_power(false);
        sd_enabled = false;
    }
    return 0;
}

bool is_sd_on(void)
{
    return sd_enabled;
}

/* SD worker thread */
void sd_worker_thread(void)
{
    sd_req_t req;
    int res;
    ssize_t bw = 0, br = 0;

    /* Attempt to mount FS - board-specific mount code may be needed */
    res = sd_mount();
    if (res != 0) {
        LOG_ERR("[SD_WORK] mount failed: %d", res);
        return;
    }

    /* Create audio directory if it doesn't exist */
    struct fs_dirent dirent;
    int stat_res = fs_stat(FILE_DATA_DIR, &dirent);
    if (stat_res < 0) {
        int mk_res = fs_mkdir(FILE_DATA_DIR);
        if (mk_res < 0) {
            LOG_ERR("[SD_WORK] mkdir %s failed: %d", FILE_DATA_DIR, mk_res);
        }
    }

    /* Print all existing audio files at boot */
    print_audio_files_at_boot();

    /* Open info file (read/write, create if not exists) */
    struct fs_dirent info_stat;
    int info_exists = fs_stat(FILE_INFO_PATH, &info_stat);
    fs_file_t_init(&fil_info);
    res = fs_open(&fil_info, FILE_INFO_PATH, FS_O_CREATE | FS_O_RDWR);
    if (res < 0) {
        LOG_ERR("[SD_WORK] open info failed: %d", res);
        return;
    } else {
        bool need_init_offset = false;
        if (info_exists < 0) {
            need_init_offset = true;
        } else if (info_stat.size < sizeof(sd_offset_info_t)) {
            need_init_offset = true;
        }
        if (need_init_offset) {
            memset(&current_offset_info, 0, sizeof(current_offset_info));
            ssize_t bw = fs_write(&fil_info, &current_offset_info, sizeof(current_offset_info));
            if (bw != sizeof(current_offset_info)) {
                LOG_ERR("[SD_WORK] init info.txt failed: %d", (int)bw);
            } else {
                fs_sync(&fil_info);
            }
        } else {
            /* Read existing offset info from info.txt */
            fs_seek(&fil_info, 0, FS_SEEK_SET);
            ssize_t rbytes = fs_read(&fil_info, &current_offset_info, sizeof(current_offset_info));
            if (rbytes != sizeof(current_offset_info)) {
                LOG_ERR("[SD_WORK] Failed to read offset info at boot: %d", (int)rbytes);
                memset(&current_offset_info, 0, sizeof(current_offset_info));
            } else {
                LOG_INF("[SD_WORK] Loaded offset info: file=%s, offset=%u",
                        current_offset_info.oldest_filename,
                        current_offset_info.offset_in_file);
            }
        }
    }

    /* Create initial audio file with timestamp */
    /* First, try to continue writing to the latest file if it's recent enough */
    res = try_continue_latest_file();
    if (res < 0) {
        /* Either no recent file found or RTC not valid - try create new file */
        res = create_audio_file_with_timestamp();
        if (res == -EAGAIN) {
            /* RTC not synced - this is OK, we'll create file when first valid data comes */
            LOG_INF("[SD_WORK] RTC not synced yet, waiting for time sync before recording");
        } else if (res < 0) {
            LOG_ERR("[SD_WORK] Failed to create initial audio file: %d", res);
            return;
        }
    }

    while (1) {
        /* Wait for a request */
        if (k_msgq_get(&sd_msgq, &req, K_FOREVER) == 0) {
            switch (req.type) {
            case REQ_WRITE_DATA:
                LOG_DBG("[SD_WORK] Buffering %u bytes to batch write", (unsigned)req.u.write.len);

                /* If no file is open yet, try to create one now */
                if (current_filename[0] == '\0') {
                    res = create_audio_file_with_timestamp();
                    if (res < 0) {
                        /* Still can't create file, discard data */
                        LOG_DBG("[SD_WORK] No file open, discarding data");
                        break;
                    }
                }

                /* Check if we need to rotate to a new file */
                if (should_rotate_file()) {
                    LOG_INF("[SD_WORK] BLE connected for >30min, rotating to new file");
                    flush_batch_buffer();
                    res = create_audio_file_with_timestamp();
                    if (res < 0) {
                        LOG_ERR("[SD_WORK] Failed to create new file for rotation: %d", res);
                    }
                    // Reset BLE connection timer
                    ble_connect_time_ms = k_uptime_get();
                }

                memcpy(write_batch_buffer + write_batch_offset, req.u.write.buf, req.u.write.len);
                write_batch_offset += req.u.write.len;
                write_batch_counter++;

                if (write_batch_counter >= WRITE_BATCH_COUNT) {
                    LOG_INF("[SD_WORK] WRITE_BATCH_COUNT reached. Flushing batch write.");
                    flush_batch_buffer();
                }

                if (bytes_since_sync >= SD_FSYNC_THRESHOLD) {
                    LOG_INF("[SD_WORK] fs_sync triggered after %u bytes", (unsigned)bytes_since_sync);
                    res = fs_sync(&fil_data);
                    if (res < 0) {
                        LOG_ERR("[SD_WORK] fs_sync data failed: %d", res);
                    }
                    bytes_since_sync = 0;
                }

                break;

            case REQ_READ_DATA:
                LOG_DBG("[SD_WORK] Reading %u bytes from file %s at offset %u",
                        (unsigned)req.u.read.length, req.u.read.filename, (unsigned)req.u.read.offset);
                
                {
                    char read_path[64];
                    build_file_path(req.u.read.filename, read_path, sizeof(read_path));
                    
                    struct fs_file_t read_file;
                    fs_file_t_init(&read_file);
                    
                    res = fs_open(&read_file, read_path, FS_O_READ);
                    if (res < 0) {
                        LOG_ERR("[SD_WORK] Failed to open file for reading: %s, err: %d", read_path, res);
                        if (req.u.read.resp) {
                            req.u.read.resp->res = res;
                            req.u.read.resp->read_bytes = 0;
                            k_sem_give(&req.u.read.resp->sem);
                        }
                        break;
                    }

                    res = fs_seek(&read_file, req.u.read.offset, FS_SEEK_SET);
                    if (res < 0) {
                        LOG_ERR("[SD_WORK] lseek failed: %d", res);
                        fs_close(&read_file);
                        if (req.u.read.resp) {
                            req.u.read.resp->res = res;
                            req.u.read.resp->read_bytes = 0;
                            k_sem_give(&req.u.read.resp->sem);
                        }
                        break;
                    }
                    
                    br = fs_read(&read_file, req.u.read.out_buf, req.u.read.length);
                    fs_close(&read_file);
                    
                    if (req.u.read.resp) {
                        req.u.read.resp->res = (br < 0) ? br : 0;
                        req.u.read.resp->read_bytes = (br < 0) ? 0 : br;
                        k_sem_give(&req.u.read.resp->sem);
                    }
                }
                break;

            case REQ_SAVE_OFFSET:
                LOG_DBG("[SD_WORK] Saving offset info: file=%s, offset=%u",
                        req.u.info.offset_info.oldest_filename,
                        req.u.info.offset_info.offset_in_file);
                
                res = fs_seek(&fil_info, 0, FS_SEEK_SET);
                if (res == 0) {
                    bw = fs_write(&fil_info, &req.u.info.offset_info, sizeof(sd_offset_info_t));
                    if (bw < 0 || bw != sizeof(sd_offset_info_t)) {
                        LOG_ERR("[SD_WORK] info write err %d", (int)bw);
                    } else {
                        res = fs_sync(&fil_info);
                        if (res < 0) {
                            LOG_ERR("[SD_WORK] fs_sync of info file failed: %d", res);
                        } else {
                            memcpy(&current_offset_info, &req.u.info.offset_info, sizeof(sd_offset_info_t));
                        }
                    }
                }
                break;

            case REQ_CLEAR_AUDIO_DIR:
                LOG_DBG("[SD_WORK] Clearing audio directory");
                
                // Flush and close current file
                flush_batch_buffer();
                fs_close(&fil_data);
                
                {
                    struct fs_dir_t dir;
                    struct fs_dirent entry;
                    char file_path[64];
                    
                    fs_dir_t_init(&dir);
                    res = fs_opendir(&dir, FILE_DATA_DIR);
                    if (res < 0) {
                        LOG_ERR("[SD_WORK] Failed to open audio dir: %d", res);
                    } else {
                        while (1) {
                            res = fs_readdir(&dir, &entry);
                            if (res < 0 || entry.name[0] == '\0') {
                                break;
                            }
                            if (entry.type == FS_DIR_ENTRY_FILE) {
                                build_file_path(entry.name, file_path, sizeof(file_path));
                                int unlink_res = fs_unlink(file_path);
                                if (unlink_res < 0 && unlink_res != -ENOENT) {
                                    LOG_ERR("[SD_WORK] Failed to delete %s: %d", file_path, unlink_res);
                                }
                            }
                        }
                        fs_closedir(&dir);
                    }
                }
                
                // Reset offset info
                memset(&current_offset_info, 0, sizeof(current_offset_info));
                fs_seek(&fil_info, 0, FS_SEEK_SET);
                fs_write(&fil_info, &current_offset_info, sizeof(current_offset_info));
                fs_sync(&fil_info);
                
                // Create a new file
                res = create_audio_file_with_timestamp();
                
                if (req.u.clear_dir.resp) {
                    req.u.clear_dir.resp->res = res;
                    k_sem_give(&req.u.clear_dir.resp->sem);
                }
                break;

            case REQ_CREATE_NEW_FILE:
                LOG_DBG("[SD_WORK] Creating new audio file");
                
                flush_batch_buffer();
                res = create_audio_file_with_timestamp();
                
                if (req.u.create_file.resp) {
                    req.u.create_file.resp->res = res;
                    k_sem_give(&req.u.create_file.resp->sem);
                }
                break;

            case REQ_GET_FILE_STATS:
                LOG_DBG("[SD_WORK] Getting file statistics");
                
                {
                    struct fs_dir_t dir;
                    struct fs_dirent entry;
                    char file_path[64];
                    uint32_t file_count = 0;
                    uint64_t total_size = 0;
                    
                    fs_dir_t_init(&dir);
                    res = fs_opendir(&dir, FILE_DATA_DIR);
                    if (res < 0) {
                        LOG_ERR("[SD_WORK] Failed to open audio dir for stats: %d", res);
                        if (req.u.file_stats.resp) {
                            req.u.file_stats.resp->res = res;
                            req.u.file_stats.resp->file_count = 0;
                            req.u.file_stats.resp->total_size = 0;
                            k_sem_give(&req.u.file_stats.resp->sem);
                        }
                        break;
                    }
                    
                    while (1) {
                        res = fs_readdir(&dir, &entry);
                        if (res < 0 || entry.name[0] == '\0') {
                            break;
                        }
                        if (entry.type == FS_DIR_ENTRY_FILE) {
                            // Check if it's a timestamp .txt file
                            char *dot = strrchr(entry.name, '.');
                            if (dot && strcmp(dot, ".txt") == 0) {
                                file_count++;
                                build_file_path(entry.name, file_path, sizeof(file_path));
                                struct fs_dirent file_stat;
                                if (fs_stat(file_path, &file_stat) == 0) {
                                    total_size += file_stat.size;
                                }
                            }
                        }
                    }
                    fs_closedir(&dir);
                    
                    if (req.u.file_stats.resp) {
                        req.u.file_stats.resp->res = 0;
                        req.u.file_stats.resp->file_count = file_count;
                        req.u.file_stats.resp->total_size = total_size;
                        k_sem_give(&req.u.file_stats.resp->sem);
                    }
                }
                break;

            default:
                LOG_ERR("[SD_WORK] unknown req type");
            }
        }
    }
}