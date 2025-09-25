#include "sd_card.h"

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/fs/ext2.h>
#include <zephyr/fs/fs.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device.h>
#include <zephyr/storage/disk_access.h>
#include <inttypes.h>
#include <string.h>

#ifndef MIN
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#endif

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#endif

LOG_MODULE_REGISTER(sd_card, CONFIG_LOG_DEFAULT_LEVEL);

// SD Card configuration
#define DISK_DRIVE_NAME "SD"
#define DISK_MOUNT_PT "/ext"
#define FS_RET_OK 0

// File management constants
#define FRAMES_PER_FILE 15000
#define SECONDS_PER_FILE 300
#define MAX_AUDIO_FILES 100
#define COUNTER_METADATA_FILE "/ext/audio/.counter"
#define MAX_FILES_PER_CHUNK 3
#define DELETION_YIELD_MS 5

// BLE storage constants
#define CV1_LOGICAL_FILE_SIZE (2 * 1024 * 1024)
#define CV1_BLE_CHUNK_SIZE 440
#define CV1_DELETE_SUCCESS 200
#define CV1_INVALID_FILE_SIZE 3
#define CV1_ZERO_FILE_SIZE 4

// BLE command definitions
#define CV1_READ_COMMAND 0
#define CV1_DELETE_COMMAND 1
#define CV1_NUKE 2
#define CV1_STOP_COMMAND 3
#define CV1_HEARTBEAT 50
#define CV1_INVALID_COMMAND 6

// Threading constants
#define CV1_STORAGE_THREAD_STACK_SIZE 4096

// SD Card mount configuration
static struct fs_mount_t mp = {
    .type = FS_EXT2,
    .flags = FS_MOUNT_FLAG_NO_FORMAT,
    .storage_dev = (void *) DISK_DRIVE_NAME,
    .mnt_point = "/ext",
};

// SD Card state variables
static bool is_mounted = false;
bool storage_is_on = false;

// File system data arrays (used by transport.c)
uint32_t file_num_array[2] = {0, 0};

// Storage health monitoring
static struct {
    uint32_t write_errors;
    uint32_t io_errors;
    uint32_t space_errors;
    uint32_t successful_writes;
    bool health_degraded;
    uint64_t last_successful_write_time;
} storage_health = {0};

static struct {
    bool auto_reformat_attempted;
    bool emergency_reformat_attempted;
    uint32_t consecutive_failures;
    bool offline_recording_disabled;
} error_recovery = {0};

// File mapping for logical concatenation
static struct {
    char filename[64];
    uint32_t file_size;
    uint32_t cumulative_offset;
} audio_file_map[MAX_AUDIO_FILES];

static uint32_t audio_file_count = 0;
static uint32_t total_logical_size = 0;
static bool file_map_initialized = false;

static void build_file_map(void);
static int find_file_for_offset(uint32_t logical_offset, uint32_t *file_index, uint32_t *file_offset);
static void update_file_map_on_write(uint32_t bytes_added);
static void invalidate_file_map(void);
static int delete_files_up_to(uint32_t logical_offset_cutoff);
static int delete_all_audio_files(bool preserve_open_file);

static uint8_t cv1_validate_delete_request(uint8_t file_num);
static int cv1_process_delete_request(uint8_t file_num);
static int cv1_process_nuke_request(void);
static void cv1_send_delete_completion(uint8_t result_code);
static void cv1_update_file_array_atomic(uint32_t new_size, uint32_t new_offset);
static bool should_close_active_file_for_delete(void);
static int close_active_file_for_delete(void);
static int reopen_file_after_delete(void);

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
// BLE storage state variables
static uint32_t cached_file_size = 0;
static volatile bool storage_initializing = false;
bool cv1_storage_active = false;
static bool cv1_pusher_should_read = false;
static atomic_t cv1_storage_ccc_enabled = ATOMIC_INIT(0);
struct bt_conn *cv1_current_connection = NULL;

// BLE command state
struct cv1_pending_cmd {
    uint8_t cmd;
    uint8_t file;
    uint32_t offset_be;
    bool valid;
};
static struct cv1_pending_cmd cv1_pending = {0};
static uint32_t cv1_read_offset = 0;
static uint32_t cv1_file_size = 0;
static uint32_t cv1_chunk_count = 0;

// BLE work queue and buffers
static struct k_work cv1_status_work;
static struct k_work_delayable cv1_data_work;
static struct k_work_delayable cv1_end_work;
static uint8_t cv1_data_buffer[CV1_BLE_CHUNK_SIZE];

// Storage thread
K_THREAD_STACK_DEFINE(cv1_storage_stack, CV1_STORAGE_THREAD_STACK_SIZE);
static struct k_thread cv1_storage_thread;
static struct k_mutex file_array_mutex;

// File deletion atomic flags
static atomic_t delete_request_flag = ATOMIC_INIT(0);
static atomic_t nuke_request_flag = ATOMIC_INIT(0);
static atomic_t delete_file_num = ATOMIC_INIT(0);
static void cv1_send_status_work_handler(struct k_work *work);
static void cv1_send_data_work_handler(struct k_work *work);
static void cv1_send_end_work_handler(struct k_work *work);
static void cv1_storage_thread_func(void *arg1, void *arg2, void *arg3);
#endif

// Audio file management
static struct fs_file_t audio_file;
static bool audio_file_open = false;
static char audio_filename[128] = "";
static uint32_t current_file_frame_count = 0;

// File counter and timestamp management
static uint32_t current_file_counter = 0;
static uint64_t base_timestamp = 1758812000;
static bool timestamp_synced = false;

// Function declarations
static void generate_filename(char *buffer, size_t buffer_size);
static uint32_t initialize_file_counter(void);
static int close_current_file(void);
static int start_new_file(void);
static int save_file_counter(uint32_t counter);
static int load_file_counter(uint32_t *counter);

// Get the device pointer for the SDHC SPI slot from the device tree
static const struct device *const sd_dev = DEVICE_DT_GET(DT_NODELABEL(sdhc0));
static const struct gpio_dt_spec sd_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

static int sd_enable_power(bool enable)
{
    int ret;
    gpio_pin_configure_dt(&sd_en, GPIO_OUTPUT);
    if (enable) {
        ret = gpio_pin_set_dt(&sd_en, 1);
        pm_device_action_run(sd_dev, PM_DEVICE_ACTION_RESUME);
    } else {
        ret = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_SUSPEND);
    }
    return ret;
}

static int sd_unmount(void)
{
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

static int sd_mount(void)
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

        if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_CTRL_INIT, NULL) != 0) {
            LOG_ERR("Storage init ERROR!");
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

    if (fs_mount(&mp) != FS_RET_OK) {
        LOG_INF("File system not found, creating file system...");
        ret = fs_mkfs(FS_EXT2, (uintptr_t) mp.storage_dev, NULL, 0);
        if (ret != 0) {
            LOG_ERR("Error formatting filesystem [%d]", ret);
            sd_enable_power(false);
            return ret;
        }

        ret = fs_mount(&mp);
        if (ret != FS_RET_OK) {
            LOG_INF("Error mounting disk %d.", ret);
            sd_enable_power(false);
            return ret;
        }
    }

    LOG_INF("Disk mounted.");
    is_mounted = true;

    (void)fs_mkdir("/ext/audio");

    current_file_counter = initialize_file_counter();
    LOG_INF("File counter set to %u after mount", current_file_counter);

    generate_filename(audio_filename, sizeof(audio_filename));
    LOG_INF("Ready with filename: %s", audio_filename);

    invalidate_file_map();

    return ret;
}

int app_sd_init(void)
{
    LOG_INF("SD card module initialized (Device: %s)", sd_dev->name);
    return 0;
}

int app_sd_off(void)
{
    sd_mount();
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    // Keep SD card mounted for offline storage
    LOG_INF("SD card kept mounted for offline storage");
#else
    sd_unmount();
#endif
    return 0;
}

// Functions needed by transport.c for offline storage
void sd_off(void)
{
    storage_is_on = false;
    sd_unmount();
}

void sd_on(void)
{
    storage_is_on = false;
    sd_mount();
}

bool is_sd_on(void)
{
    return is_mounted;
}

static uint64_t get_current_timestamp(void) {
    return base_timestamp + (current_file_counter * SECONDS_PER_FILE);
}

static void generate_filename(char *buffer, size_t buffer_size) {
    int n;
    uint64_t ts = get_current_timestamp();
    n = snprintk(buffer, buffer_size, "/ext/audio/a01_fs160_%" PRIu64 ".bin", ts);
    if (n < 0 || (size_t)n >= buffer_size) {
        snprintk(buffer, buffer_size, "/ext/audio/a01.bin");
        LOG_WRN("Filename truncated, using fallback: %s", buffer);
    } else {
        LOG_DBG("Generated filename: %s", buffer);
    }
}

static uint32_t extract_counter_from_filename(const char* filename) {
    const char* prefix = "a01_fs160_";
    const char* suffix = ".bin";

    size_t filename_len = strlen(filename);
    if (filename_len < strlen(prefix) + 10 + strlen(suffix)) {
        return 0;
    }

    if (strncmp(filename, prefix, strlen(prefix)) != 0) {
        return 0;
    }

    if (strcmp(filename + filename_len - strlen(suffix), suffix) != 0) {
        return 0;
    }

    const char* timestamp_start = filename + strlen(prefix);
    size_t timestamp_len = filename_len - strlen(prefix) - strlen(suffix);

    if (timestamp_len > 20) {
        return 0;
    }

    char timestamp_str[32];
    strncpy(timestamp_str, timestamp_start, timestamp_len);
    timestamp_str[timestamp_len] = '\0';

    for (size_t i = 0; i < timestamp_len; i++) {
        if (timestamp_str[i] < '0' || timestamp_str[i] > '9') {
            return 0;
        }
    }

    uint64_t timestamp = strtoull(timestamp_str, NULL, 10);

    if (timestamp < base_timestamp) {
        return 0;
    }

    uint32_t counter = (uint32_t)((timestamp - base_timestamp) / SECONDS_PER_FILE);
    return counter;
}

static uint32_t scan_existing_files(void) {
    struct fs_dir_t dir;
    struct fs_dirent entry;
    uint32_t highest_counter = 0;
    uint32_t file_count = 0;
    uint32_t start_time = k_uptime_get_32();

    if (fs_opendir(&dir, "/ext/audio") != 0) {
        LOG_DBG("No audio directory found");
        return 0;
    }

    while (fs_readdir(&dir, &entry) == 0 && entry.name[0] != '\0') {
        file_count++;

        if (file_count > 2000) {
            LOG_WRN("Too many files, stopping scan at %u", file_count);
            break;
        }

        if (k_uptime_get_32() - start_time > 5000) {
            LOG_WRN("Scan timeout, stopping at %u files", file_count);
            break;
        }

        if (strstr(entry.name, "a01_fs160_") == entry.name) {
            // Extract timestamp and calculate counter
            uint32_t counter = extract_counter_from_filename(entry.name);
            if (counter > highest_counter) {
                highest_counter = counter;
            }
        }
    }

    fs_closedir(&dir);
    LOG_DBG("Scanned %u files, highest counter: %u", file_count, highest_counter);
    return highest_counter;
}

static uint32_t initialize_file_counter(void) {
    uint32_t scanned_counter = scan_existing_files();
    uint32_t saved_counter = 0;
    uint32_t final_counter = 0;

    if (load_file_counter(&saved_counter) == 0) {
        LOG_DBG("Loaded persistent counter: %u", saved_counter);
    } else {
        saved_counter = 0;
    }

    if (scanned_counter > 0) {
        final_counter = scanned_counter + 1;
        LOG_INF("Using scanned counter + 1: %u", final_counter);
    } else if (saved_counter > 0) {
        final_counter = saved_counter;
        LOG_INF("Using saved counter: %u", final_counter);
    } else {
        final_counter = 0;
        LOG_INF("Fresh start, counter = 0");
    }

    if (save_file_counter(final_counter) != 0) {
        LOG_WRN("Failed to save counter to persistent storage");
    }

    return final_counter;
}

uint32_t get_current_file_counter(void) {
    return current_file_counter;
}

uint64_t get_base_timestamp(void) {
    return base_timestamp;
}

void set_base_timestamp(uint64_t timestamp) {
    base_timestamp = timestamp;
    timestamp_synced = true;
    LOG_INF("Base timestamp updated to: %" PRIu64, base_timestamp);
}

static void update_storage_health(bool success, int error_code) {
    if (success) {
        storage_health.successful_writes++;
        storage_health.last_successful_write_time = k_uptime_get();
        error_recovery.consecutive_failures = 0;

        if (storage_health.successful_writes % 100 == 0) {
            storage_health.health_degraded = false;
        }
    } else {
        storage_health.write_errors++;
        error_recovery.consecutive_failures++;

        switch (error_code) {
            case -ENOSPC:
                storage_health.space_errors++;
                break;
            case -EIO:
                storage_health.io_errors++;
                break;
        }

        if (error_recovery.consecutive_failures >= 5) {
            storage_health.health_degraded = true;
            LOG_WRN("Storage health degraded: %u consecutive failures",
                    error_recovery.consecutive_failures);
        }

        if (error_recovery.consecutive_failures >= 20) {
            error_recovery.offline_recording_disabled = true;
            LOG_ERR("Offline recording disabled due to critical storage failures");
        }
    }
}

static bool is_offline_recording_available(void) {
    return !error_recovery.offline_recording_disabled &&
           is_mounted &&
           !storage_health.health_degraded;
}

static int close_current_file(void) {
    if (!audio_file_open) {
        return 0;
    }

    int ret = fs_close(&audio_file);
    if (ret < 0) {
        LOG_ERR("Failed to close current file: %d", ret);
    } else {
        LOG_DBG("Closed file %s after %u frames", audio_filename, current_file_frame_count);
    }

    audio_file_open = false;
    return ret;
}

static int save_file_counter(uint32_t counter) {
    struct fs_file_t counter_file;
    fs_file_t_init(&counter_file);

    int ret = fs_open(&counter_file, COUNTER_METADATA_FILE, FS_O_CREATE | FS_O_WRITE);
    if (ret != 0) {
        LOG_ERR("Failed to open counter file for writing: %d", ret);
        return ret;
    }

    ret = fs_write(&counter_file, &counter, sizeof(counter));
    fs_close(&counter_file);

    if (ret == sizeof(counter)) {
        return 0;
    } else {
        LOG_ERR("Failed to write counter: %d", ret);
        return -EIO;
    }
}

static int load_file_counter(uint32_t *counter) {
    struct fs_file_t counter_file;
    fs_file_t_init(&counter_file);

    int ret = fs_open(&counter_file, COUNTER_METADATA_FILE, FS_O_READ);
    if (ret != 0) {
        *counter = 0;
        return 0;
    }

    ret = fs_read(&counter_file, counter, sizeof(*counter));
    fs_close(&counter_file);

    if (ret == sizeof(*counter)) {
        return 0;
    } else {
        LOG_ERR("Failed to read counter: %d", ret);
        *counter = 0;
        return -EIO;
    }
}

static int start_new_file(void) {
    current_file_counter++;

    int save_ret = save_file_counter(current_file_counter);
    if (save_ret != 0) {
        LOG_WRN("Failed to save file counter: %d", save_ret);
    }

    generate_filename(audio_filename, sizeof(audio_filename));
    current_file_frame_count = 0;

    int ret = fs_mkdir("/ext/audio");
    if (ret != 0 && ret != -EEXIST) {
        LOG_ERR("Failed to create audio directory: %d", ret);
        if (ret == -ENOSPC) {
            LOG_ERR("SD card full - cannot create audio directory");
            return -ENOSPC;
        } else if (ret == -EIO) {
            LOG_ERR("SD card I/O error during directory creation");
            return -EIO;
        }
        return ret;
    }

    int retry_count = 0;
    while (retry_count < 10) {
        struct fs_dirent stat_buf;
        ret = fs_stat(audio_filename, &stat_buf);

        if (ret == 0) {
            LOG_DBG("File %s exists, deleting", audio_filename);
            ret = fs_unlink(audio_filename);
            if (ret != 0) {
                LOG_ERR("Failed to delete existing file %s: %d", audio_filename, ret);
                return ret;
            }
        } else if (ret != -ENOENT) {
            LOG_ERR("Failed to stat file %s: %d", audio_filename, ret);
            return ret;
        }

        fs_file_t_init(&audio_file);
        ret = fs_open(&audio_file, audio_filename, FS_O_CREATE | FS_O_WRITE);

        if (ret == 0) {
            break;
        } else {
            LOG_ERR("Failed to open new audio file %s: %d", audio_filename, ret);
            if (ret == -ENOSPC) {
                LOG_ERR("SD card full - cannot create new audio file");
                return -ENOSPC;
            } else if (ret == -EIO) {
                LOG_ERR("SD card I/O error during file creation");
                return -EIO;
            } else if (ret == -EINVAL) {
                LOG_ERR("Invalid filename or parameters: %s", audio_filename);
                return -EINVAL;
            }
            return ret;
        }
    }

    if (retry_count >= 10) {
        LOG_ERR("Too many file collisions, giving up");
        return -EAGAIN;
    }

    audio_file_open = true;
    LOG_INF("Started new file %s (counter=%u)", audio_filename, current_file_counter);

    if (audio_file_count < MAX_AUDIO_FILES) {
        strncpy(audio_file_map[audio_file_count].filename, audio_filename,
                sizeof(audio_file_map[audio_file_count].filename) - 1);
        audio_file_map[audio_file_count].filename[sizeof(audio_file_map[audio_file_count].filename) - 1] = '\0';
        audio_file_map[audio_file_count].file_size = 0;
        audio_file_map[audio_file_count].cumulative_offset = total_logical_size;
        audio_file_count++;
        file_map_initialized = true;
    } else {
        LOG_WRN("File map full, cannot track new file");
    }

    return 0;
}

int write_to_file(uint8_t *data, uint32_t length)
{
    if (!is_mounted) {
        LOG_ERR("SD card not mounted");
        update_storage_health(false, -ENODEV);
        return -1;
    }

    if (!is_offline_recording_available()) {
        LOG_DBG("Offline recording unavailable");
        return -EACCES;
    }

    // Open audio file if not already open
    if (!audio_file_open) {
        // Create audio directory first
        int ret = fs_mkdir("/ext/audio");
        if (ret != 0 && ret != -EEXIST) {
            LOG_ERR("Failed to create audio directory: %d", ret);
            return -1;
        }

        if (audio_filename[0] == '\0') {
            generate_filename(audio_filename, sizeof(audio_filename));
            LOG_WRN("audio_filename was empty, generated: %s", audio_filename);
        }

        int retry_count = 0;
        while (retry_count < 10) {
            struct fs_dirent stat_buf;
            ret = fs_stat(audio_filename, &stat_buf);

            if (ret == 0) {
                LOG_WRN("File %s exists, incrementing counter", audio_filename);
                current_file_counter++;
                generate_filename(audio_filename, sizeof(audio_filename));
                retry_count++;
                continue;
            } else if (ret != -ENOENT) {
                LOG_ERR("Failed to stat file %s: %d", audio_filename, ret);
                return -1;
            }

            fs_file_t_init(&audio_file);
            ret = fs_open(&audio_file, audio_filename, FS_O_CREATE | FS_O_WRITE);

            if (ret == 0) {
                break;
            } else {
                LOG_ERR("Failed to open audio file %s: %d", audio_filename, ret);
                return -1;
            }
        }

        if (retry_count >= 10) {
            LOG_ERR("Too many file collisions during initial open, giving up");
            return -1;
        }
        audio_file_open = true;
        current_file_frame_count = 0;
        LOG_DBG("Audio file %s opened for writing", audio_filename);
    }

    ssize_t bytes_written = fs_write(&audio_file, data, length);
    if (bytes_written < 0) {
        LOG_ERR("Failed to write to audio file: %d", (int)bytes_written);

        switch (bytes_written) {
            case -ENOSPC:
                LOG_ERR("SD card full or filesystem corruption detected");
                fs_close(&audio_file);
                audio_file_open = false;

                if (!error_recovery.auto_reformat_attempted) {
                    LOG_INF("Attempting automatic SD card reformat");
                    error_recovery.auto_reformat_attempted = true;
                    int reformat_ret = force_sd_reformat();
                    if (reformat_ret == 0) {
                        LOG_INF("Auto-reformat successful, retrying write");
                        current_file_frame_count = 0;
                        error_recovery.consecutive_failures = 0;
                        storage_health.health_degraded = false;
                        return write_to_file(data, length);
                    } else {
                        LOG_ERR("Auto-reformat failed: %d", reformat_ret);
                        error_recovery.offline_recording_disabled = true;
                    }
                } else {
                    LOG_ERR("SD card full and reformat already attempted");
                    error_recovery.offline_recording_disabled = true;
                }
                break;

            case -EIO:
                LOG_ERR("SD card I/O error");
                fs_close(&audio_file);
                audio_file_open = false;
                break;

            case -EBADF:
                LOG_ERR("Invalid file descriptor");
                fs_close(&audio_file);
                audio_file_open = false;
                break;

            case -EINVAL:
                LOG_ERR("Invalid write parameters - data=%p, length=%u", data, length);
                break;

            default:
                LOG_ERR("Unexpected write error: %d", (int)bytes_written);
                fs_close(&audio_file);
                audio_file_open = false;
                break;
        }

        update_storage_health(false, (int)bytes_written);
        return (int)bytes_written;
    }

    if (bytes_written != (ssize_t)length) {
        LOG_WRN("Partial write: expected %u bytes, wrote %d bytes", length, (int)bytes_written);
    }

    uint32_t frames_in_write = 0;
    uint8_t *data_ptr = data;
    uint32_t remaining = length;

    while (remaining >= 4) {
        uint32_t frame_len = data_ptr[0] | (data_ptr[1] << 8) | (data_ptr[2] << 16) | (data_ptr[3] << 24);

        if (frame_len == 0 || frame_len > remaining - 4) {
            break;
        }

        frames_in_write++;
        uint32_t total_frame_size = 4 + frame_len;

        if (total_frame_size > remaining) {
            break;
        }

        data_ptr += total_frame_size;
        remaining -= total_frame_size;
    }

    current_file_frame_count += frames_in_write;

    if (current_file_frame_count >= FRAMES_PER_FILE) {
        LOG_INF("File rollover triggered: %u frames", current_file_frame_count);

        close_current_file();

        int new_file_ret = start_new_file();
        if (new_file_ret == 0) {
            k_mutex_lock(&file_array_mutex, K_FOREVER);
            file_num_array[1] = 0;
            k_mutex_unlock(&file_array_mutex);
        } else {
            LOG_ERR("Failed to start new file during rollover: %d", new_file_ret);

            if (new_file_ret == -ENOSPC) {
                LOG_ERR("SD card full during rollover");
                static bool emergency_reformat = false;
                if (!emergency_reformat) {
                    emergency_reformat = true;
                    int reformat_ret = force_sd_reformat();
                    if (reformat_ret == 0) {
                        LOG_INF("Emergency reformat successful");
                        current_file_frame_count = 0;
                        return write_to_file(data, length);
                    }
                }
            }

            LOG_ERR("Rollover recovery failed");
            return -1;
        }
    }

    k_mutex_lock(&file_array_mutex, K_FOREVER);
    file_num_array[1] += bytes_written;
    file_num_array[0] += bytes_written;

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    cached_file_size = file_num_array[0];
#endif
    k_mutex_unlock(&file_array_mutex);

    static int write_count = 0;
    if ((write_count++ % 100) == 0) {
        LOG_DBG("Wrote %d bytes (%u frames) total: %u bytes",
                (int)bytes_written, frames_in_write, file_num_array[1]);
    }

    update_storage_health(true, 0);
    update_file_map_on_write(bytes_written);

    return (int)bytes_written;
}

uint32_t get_file_size(uint8_t num)
{
    if (!file_map_initialized) {
        build_file_map();
    }

    k_mutex_lock(&file_array_mutex, K_FOREVER);
    file_num_array[0] = total_logical_size;
    k_mutex_unlock(&file_array_mutex);
    return total_logical_size;
}

int get_offset(void)
{
    if (!file_map_initialized) {
        build_file_map();
    }

    return total_logical_size;
}

struct storage_health_info get_storage_health(void) {
    struct storage_health_info info = {
        .write_errors = storage_health.write_errors,
        .io_errors = storage_health.io_errors,
        .space_errors = storage_health.space_errors,
        .successful_writes = storage_health.successful_writes,
        .health_degraded = storage_health.health_degraded,
        .offline_recording_disabled = error_recovery.offline_recording_disabled,
        .consecutive_failures = error_recovery.consecutive_failures
    };
    return info;
}

bool is_storage_healthy(void) {
    return !storage_health.health_degraded &&
           !error_recovery.offline_recording_disabled &&
           error_recovery.consecutive_failures < 5;
}

void reset_storage_health(void) {
    LOG_DBG("Resetting storage health monitoring");
    memset(&storage_health, 0, sizeof(storage_health));
    memset(&error_recovery, 0, sizeof(error_recovery));
    storage_health.last_successful_write_time = k_uptime_get();
}

int read_logical_file(uint32_t offset, uint8_t *buffer, uint32_t length) {
    if (!buffer || length == 0) {
        return -EINVAL;
    }

    if (!is_mounted) {
        LOG_ERR("SD card not mounted");
        return -ENODEV;
    }

    // Ensure file map is initialized
    if (!file_map_initialized) {
        build_file_map();
    }

    uint32_t bytes_read_total = 0;
    uint32_t remaining_to_read = length;
    uint32_t current_logical_offset = offset;

    // Read across multiple files if necessary
    while (remaining_to_read > 0 && current_logical_offset < total_logical_size) {
        uint32_t file_index, file_offset;
        int ret = find_file_for_offset(current_logical_offset, &file_index, &file_offset);
        if (ret < 0) {
            break; // Beyond available data
        }

        // Calculate how much to read from this file
        uint32_t file_remaining = audio_file_map[file_index].file_size - file_offset;
        uint32_t to_read = MIN(remaining_to_read, file_remaining);

        // Open and read from the specific file
        struct fs_file_t read_file;
        fs_file_t_init(&read_file);
        if (fs_open(&read_file, audio_file_map[file_index].filename, FS_O_READ) == 0) {
            if (fs_seek(&read_file, file_offset, FS_SEEK_SET) == 0) {
                ssize_t bytes_read = fs_read(&read_file, buffer + bytes_read_total, to_read);
                if (bytes_read > 0) {
                    bytes_read_total += bytes_read;
                    remaining_to_read -= bytes_read;
                    current_logical_offset += bytes_read;

                    if (bytes_read < (ssize_t)to_read) {
                        break;
                    }
                } else {
                    break;
                }
            } else {
                LOG_WRN("Failed to seek in %s", audio_file_map[file_index].filename);
            }
            fs_close(&read_file);
        } else {
            LOG_WRN("Failed to open %s", audio_file_map[file_index].filename);
            break;
        }
    }

    return bytes_read_total;
}

uint32_t get_logical_file_size(void) {
    if (!file_map_initialized) {
        build_file_map();
    }
    return total_logical_size;
}

void rebuild_file_map(void) {
    invalidate_file_map();
    build_file_map();
}


static void build_file_map(void) {

    audio_file_count = 0;
    total_logical_size = 0;

    struct fs_dir_t dir;
    fs_dir_t_init(&dir);

    int ret = fs_opendir(&dir, "/ext/audio");
    if (ret < 0) {
        LOG_WRN("Failed to open audio directory: %d", ret);
        file_map_initialized = true; // Mark as initialized even if empty
        return;
    }

    struct fs_dirent entry;
    while (fs_readdir(&dir, &entry) == 0 && entry.name[0] != '\0') {
        // Skip directories and non-audio files
        if (entry.type != FS_DIR_ENTRY_FILE ||
            strncmp(entry.name, "a01_fs160_", 10) != 0 ||
            !strstr(entry.name, ".bin")) {
            continue;
        }

        if (audio_file_count >= MAX_AUDIO_FILES) {
            LOG_WRN("Too many audio files, stopping at %u", MAX_AUDIO_FILES);
            break;
        }

        char full_path[128];
        snprintf(full_path, sizeof(full_path), "/ext/audio/%s", entry.name);

        struct fs_dirent stat_info;
        ret = fs_stat(full_path, &stat_info);
        if (ret < 0) {
            LOG_WRN("Failed to stat %s: %d", full_path, ret);
            continue;
        }

        strncpy(audio_file_map[audio_file_count].filename, full_path,
                sizeof(audio_file_map[audio_file_count].filename) - 1);
        audio_file_map[audio_file_count].filename[sizeof(audio_file_map[audio_file_count].filename) - 1] = '\0';
        audio_file_map[audio_file_count].file_size = stat_info.size;
        audio_file_map[audio_file_count].cumulative_offset = total_logical_size;

        total_logical_size += stat_info.size;
        audio_file_count++;
    }

    fs_closedir(&dir);
    file_map_initialized = true;

    LOG_DBG("File map built: %u files, total size=%u bytes",
            audio_file_count, total_logical_size);
}

static int find_file_for_offset(uint32_t logical_offset, uint32_t *file_index, uint32_t *file_offset) {
    if (!file_map_initialized) {
        build_file_map();
    }

    for (uint32_t i = 0; i < audio_file_count; i++) {
        uint32_t file_start = audio_file_map[i].cumulative_offset;
        uint32_t file_end = file_start + audio_file_map[i].file_size;

        if (logical_offset >= file_start && logical_offset < file_end) {
            *file_index = i;
            *file_offset = logical_offset - file_start;
            return 0;
        }
    }

    return -ERANGE;
}

static void update_file_map_on_write(uint32_t bytes_added) {
    if (!file_map_initialized) {
        return;
    }

    if (audio_file_count > 0) {
        audio_file_map[audio_file_count - 1].file_size += bytes_added;
        total_logical_size += bytes_added;
    }
}

static void invalidate_file_map(void) {
    file_map_initialized = false;
}

static int delete_files_up_to(uint32_t logical_offset_cutoff) {
    LOG_INF("Deleting files up to offset %u", logical_offset_cutoff);

    if (!is_mounted) {
        LOG_ERR("SD card not mounted");
        return -ENODEV;
    }

    if (!file_map_initialized) {
        build_file_map();
        k_msleep(DELETION_YIELD_MS);
    }

    uint32_t files_removed = 0;
    uint32_t files_failed = 0;
    uint32_t files_processed = 0;
    int first_error = 0;
    bool active_file_was_deleted = false;

    for (uint32_t i = 0; i < audio_file_count; i++) {
        uint32_t file_start = audio_file_map[i].cumulative_offset;
        uint32_t file_end = file_start + audio_file_map[i].file_size;

        if (file_end <= logical_offset_cutoff) {
            bool is_active_file = (audio_file_open && strstr(audio_file_map[i].filename, audio_filename) != NULL);
            bool need_reopen = false;

            if (is_active_file) {
                LOG_DBG("Closing active file %s for deletion", audio_filename);
                int ret = close_current_file();
                if (ret != 0) {
                    LOG_ERR("Failed to close active file: %d", ret);
                    files_failed++;
                    if (first_error == 0) {
                        first_error = ret;
                    }
                    continue;
                }
                need_reopen = true;
            }

            int ret = fs_unlink(audio_file_map[i].filename);
            if (ret == 0) {
                LOG_DBG("Deleted %s", audio_file_map[i].filename);
                files_removed++;
                if (need_reopen) {
                    active_file_was_deleted = true;
                }
            } else if (ret == -ENOENT) {
                LOG_DBG("%s already deleted", audio_file_map[i].filename);
                files_removed++;
                if (need_reopen) {
                    active_file_was_deleted = true;
                }
            } else {
                LOG_ERR("Failed to delete %s: %d", audio_file_map[i].filename, ret);
                files_failed++;
                if (first_error == 0) {
                    first_error = ret;
                }
            }

            files_processed++;

            if (files_processed % MAX_FILES_PER_CHUNK == 0) {
                k_msleep(DELETION_YIELD_MS);
            }
        }
    }

    k_msleep(DELETION_YIELD_MS);
    invalidate_file_map();
    build_file_map();

    if (active_file_was_deleted && files_failed == 0) {
        LOG_INF("Active file was deleted, starting new file");

        int reopen_ret = start_new_file();

        if (reopen_ret == 0) {
            k_mutex_lock(&file_array_mutex, K_FOREVER);
            file_num_array[1] = 0;
            k_mutex_unlock(&file_array_mutex);
            LOG_DBG("New file started after deletion");
        } else {
            LOG_ERR("Failed to reopen file after deletion: %d", reopen_ret);
            return reopen_ret;
        }
    }

    LOG_INF("Deleted %u files, %u failed, remaining: %u bytes",
            files_removed, files_failed, total_logical_size);

    return (files_failed > 0) ? first_error : 0;
}

static int delete_all_audio_files(bool preserve_open_file) {
    LOG_INF("Deleting all audio files, preserve_open=%d", preserve_open_file);

    if (!is_mounted) {
        LOG_ERR("SD card not mounted");
        return -ENODEV;
    }

    uint32_t files_removed = 0;
    uint32_t files_failed = 0;
    uint32_t files_processed = 0;
    int first_error = 0;
    bool active_file_was_deleted = false;

    struct fs_dir_t dir;
    fs_dir_t_init(&dir);

    int ret = fs_opendir(&dir, "/ext/audio");
    if (ret < 0) {
        LOG_ERR("Failed to open audio directory: %d", ret);
        return ret;
    }

    struct fs_dirent entry;
    while (fs_readdir(&dir, &entry) == 0 && entry.name[0] != '\0') {
        if (entry.type != FS_DIR_ENTRY_FILE ||
            strncmp(entry.name, "a01_fs160_", 10) != 0 ||
            !strstr(entry.name, ".bin")) {
            continue;
        }

        char full_path[128];
        snprintf(full_path, sizeof(full_path), "/ext/audio/%s", entry.name);

        bool is_active_file = (audio_file_open && strstr(full_path, audio_filename) != NULL);
        bool need_reopen = false;

        if (is_active_file) {
            LOG_DBG("Closing active file %s for deletion", audio_filename);
            ret = close_current_file();
            if (ret != 0) {
                LOG_ERR("Failed to close active file: %d", ret);
                files_failed++;
                if (first_error == 0) {
                    first_error = ret;
                }
                continue;
            }
            need_reopen = true;
        }

        ret = fs_unlink(full_path);
        if (ret == 0) {
            LOG_DBG("Deleted %s", full_path);
            files_removed++;
            if (need_reopen) {
                active_file_was_deleted = true;
            }
        } else if (ret == -ENOENT) {
            LOG_DBG("%s already deleted", full_path);
            files_removed++;
            if (need_reopen) {
                active_file_was_deleted = true;
            }
        } else {
            LOG_ERR("Failed to delete %s: %d", full_path, ret);
            files_failed++;
            if (first_error == 0) {
                first_error = ret;
            }
        }

        files_processed++;

        if (files_processed % MAX_FILES_PER_CHUNK == 0) {
            k_msleep(DELETION_YIELD_MS);
        }
    }

    fs_closedir(&dir);

    k_msleep(DELETION_YIELD_MS);
    invalidate_file_map();
    build_file_map();

    if (active_file_was_deleted && files_failed == 0) {
        LOG_INF("Active file was deleted, starting new file");

        int reopen_ret = start_new_file();

        if (reopen_ret == 0) {
            k_mutex_lock(&file_array_mutex, K_FOREVER);
            file_num_array[1] = 0;
            k_mutex_unlock(&file_array_mutex);
            LOG_DBG("New file started after deletion");
        } else {
            LOG_ERR("Failed to reopen file after deletion: %d", reopen_ret);
            return reopen_ret;
        }
    }

    LOG_INF("Deleted %u files, %u failed, remaining: %u bytes",
            files_removed, files_failed, total_logical_size);

    return (files_failed > 0) ? first_error : 0;
}

int force_sd_reformat(void)
{
    LOG_INF("Reformatting SD card");

    if (audio_file_open) {
        fs_close(&audio_file);
        audio_file_open = false;
        LOG_DBG("Closed audio file");
    }

    int ret = sd_unmount();
    if (ret) {
        LOG_ERR("Failed to unmount SD card: %d", ret);
    }

    ret = fs_mkfs(FS_EXT2, (uintptr_t) DISK_DRIVE_NAME, NULL, 0);
    if (ret != 0) {
        LOG_ERR("Error formatting filesystem [%d]", ret);
        return ret;
    }
    LOG_INF("SD card formatted successfully");

    ret = sd_mount();
    if (ret) {
        LOG_ERR("Failed to remount after format: %d", ret);
        return ret;
    }

    file_num_array[0] = 0;
    file_num_array[1] = 0;
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    cached_file_size = 0;
#endif

    storage_health.write_errors = 0;
    storage_health.io_errors = 0;
    storage_health.space_errors = 0;
    storage_health.health_degraded = false;
    error_recovery.consecutive_failures = 0;
    storage_health.last_successful_write_time = k_uptime_get();

    invalidate_file_map();

    LOG_INF("SD card reformat complete");
    return 0;
}

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
static struct bt_uuid_128 cv1_storage_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295780, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 cv1_storage_write_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295781, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 cv1_storage_read_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295782, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));

// Forward declarations for CV1 storage handlers
static ssize_t cv1_storage_read_characteristic(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               void *buf,
                                               uint16_t len,
                                               uint16_t offset);
static ssize_t cv1_storage_write_handler(struct bt_conn *conn,
                                         const struct bt_gatt_attr *attr,
                                         const void *buf,
                                         uint16_t len,
                                         uint16_t offset,
                                         uint8_t flags);
static void cv1_storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static uint8_t cv1_parse_storage_command(uint8_t command, uint8_t file_num, uint32_t offset_be, bool replayed);
static void cv1_schedule_data_send(void);
static size_t cv1_pack_next_ble_chunk(uint8_t out[CV1_BLE_CHUNK_SIZE], uint32_t *chunk_offset);
static int cv1_read_bytes(uint32_t logical_offset, uint8_t *dest, size_t len);
static int cv1_notify_storage(const uint8_t *data, uint16_t len);
static void cv1_reset_stream_state(void);
static void cv1_send_status_code(uint8_t code);

// CV1 Storage Service attributes
static struct bt_gatt_attr cv1_storage_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&cv1_storage_service_uuid),
    BT_GATT_CHARACTERISTIC(&cv1_storage_write_uuid.uuid,
                           BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_WRITE,
                           NULL,
                           cv1_storage_write_handler,
                           NULL),
    BT_GATT_CCC(cv1_storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&cv1_storage_read_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ,
                           cv1_storage_read_characteristic,
                           NULL,
                           NULL),
    BT_GATT_CCC(cv1_storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

// CV1 Storage Service declaration
struct bt_gatt_service storage_service = BT_GATT_SERVICE(cv1_storage_service_attr);

static uint8_t cv1_validate_delete_request(uint8_t file_num) {
    if (file_num == 0) {
        return CV1_INVALID_FILE_SIZE;
    }

    if (!file_map_initialized) {
        build_file_map();
    }

    if (file_num != 1) {
        LOG_WRN("CV1 only supports file_num=1, got %u", file_num);
        return CV1_INVALID_FILE_SIZE;
    }

    if (total_logical_size == 0) {
        return CV1_ZERO_FILE_SIZE;
    }

    return 0;
}

static void cv1_update_file_array_atomic(uint32_t new_size, uint32_t new_offset) {
    k_mutex_lock(&file_array_mutex, K_FOREVER);
    file_num_array[0] = new_size;
    file_num_array[1] = new_offset;
    cached_file_size = new_size;
    k_mutex_unlock(&file_array_mutex);
}

static void cv1_reset_stream_state(void)
{
    cv1_chunk_count = 0;
}

static int cv1_notify_storage(const uint8_t *data, uint16_t len)
{
    if (!atomic_get(&cv1_storage_ccc_enabled)) {
        return -EACCES;
    }

    if (!cv1_current_connection) {
        return -ENOTCONN;
    }

    return bt_gatt_notify(cv1_current_connection, &storage_service.attrs[1], data, len);
}

static void cv1_send_status_code(uint8_t code)
{
    uint8_t status_buffer[1] = {code};
    cv1_notify_storage(status_buffer, 1);
}

static void cv1_schedule_data_send(void)
{
    if (!cv1_storage_active) {
        return;
    }

    k_work_cancel_delayable(&cv1_data_work);
    k_work_cancel_delayable(&cv1_end_work);
    cv1_pusher_should_read = false;
    k_work_schedule(&cv1_data_work, K_NO_WAIT);
}

static int cv1_read_bytes(uint32_t logical_offset, uint8_t *dest, size_t len)
{
    if (len == 0) {
        return 0;
    }

    if (!file_map_initialized) {
        build_file_map();
    }

    size_t copied = 0;
    while (copied < len && logical_offset < cv1_file_size) {
        uint32_t file_index;
        uint32_t file_offset;
        int ret = find_file_for_offset(logical_offset, &file_index, &file_offset);
        if (ret < 0) {
            break;
        }

        uint32_t available = audio_file_map[file_index].file_size - file_offset;
        size_t to_read = MIN(len - copied, available);
        if (to_read == 0) {
            break;
        }

        struct fs_file_t read_file;
        fs_file_t_init(&read_file);
        ret = fs_open(&read_file, audio_file_map[file_index].filename, FS_O_READ);
        if (ret != 0) {
            break;
        }

        ret = fs_seek(&read_file, file_offset, FS_SEEK_SET);
        if (ret != 0) {
            fs_close(&read_file);
            break;
        }

        ssize_t bytes = fs_read(&read_file, dest + copied, to_read);
        fs_close(&read_file);
        if (bytes <= 0) {
            break;
        }

        copied += (size_t)bytes;
        logical_offset += (uint32_t)bytes;

        if ((size_t)bytes < to_read) {
            break;
        }
    }

    return (int)copied;
}

static size_t cv1_pack_next_ble_chunk(uint8_t out[CV1_BLE_CHUNK_SIZE], uint32_t *chunk_offset)
{
    if (chunk_offset) {
        *chunk_offset = cv1_read_offset;
    }

    if (cv1_read_offset >= cv1_file_size) {
        return 0;
    }

    size_t remaining = cv1_file_size - cv1_read_offset;
    size_t to_copy = MIN(remaining, CV1_BLE_CHUNK_SIZE);

    memset(out, 0, CV1_BLE_CHUNK_SIZE);

    int read = cv1_read_bytes(cv1_read_offset, out, to_copy);
    if (read <= 0) {
        cv1_read_offset = cv1_file_size;
        return 0;
    }

    size_t bytes_read = (size_t)read;
    cv1_read_offset += bytes_read;


    return CV1_BLE_CHUNK_SIZE;
}

static int cv1_process_delete_request(uint8_t file_num) {
    uint8_t validation_result = cv1_validate_delete_request(file_num);
    if (validation_result != 0) {
        return validation_result;
    }

    int result = delete_all_audio_files(false);

    if (result == 0) {
        cv1_update_file_array_atomic(0, 0);
        current_file_counter = 0;
        save_file_counter(0);
        LOG_INF("All files deleted, counter reset");
    } else {
        LOG_ERR("Filesystem deletion failed: %d", result);
    }

    return result;
}

static int cv1_process_nuke_request(void) {
    int result = delete_all_audio_files(true);

    if (result == 0) {
        cv1_update_file_array_atomic(0, 0);
        current_file_counter = 0;
        save_file_counter(0);
        LOG_INF("All files nuked, counter reset");
    } else {
        LOG_ERR("Nuke deletion failed: %d", result);
    }

    return result;
}

static void cv1_send_delete_completion(uint8_t result_code) {
    if (cv1_current_connection) {
        uint8_t result_buffer[1] = {result_code};
        cv1_notify_storage(result_buffer, 1);
    }
}

static bool should_close_active_file_for_delete(void) {
    return (cv1_current_connection != NULL && cv1_storage_active);
}

static bool file_closed_for_deletion = false;
static int close_active_file_for_delete(void) {
    if (!audio_file_open) {
        return 0;
    }

    int ret = close_current_file();
    if (ret != 0) {
        LOG_ERR("Failed to close active file: %d", ret);
        return ret;
    }

    file_closed_for_deletion = true;
    return 0;
}

static int reopen_file_after_delete(void) {
    if (!file_closed_for_deletion) {
        return 0;
    }

    if (!cv1_current_connection) {
        LOG_DBG("Reopening file for offline recording");
        file_closed_for_deletion = false;
        return start_new_file();
    }
    return 0;
}


static void cv1_send_status_work_handler(struct k_work *work)
{
    (void)work;
}


void cv1_read_file_data_in_pusher(void)
{
    if (!cv1_storage_active || !cv1_pusher_should_read) {
        return;
    }

    cv1_pusher_should_read = false;
    cv1_schedule_data_send();
}

static void cv1_send_data_work_handler(struct k_work *work)
{
    (void)work;

    if (!cv1_storage_active) {
        return;
    }

    if (cv1_read_offset >= cv1_file_size) {
        k_work_schedule(&cv1_end_work, K_NO_WAIT);
        return;
    }

    uint32_t chunk_offset = cv1_read_offset;
    size_t produced = cv1_pack_next_ble_chunk(cv1_data_buffer, &chunk_offset);

    if (produced == 0) {
        k_work_schedule(&cv1_end_work, K_NO_WAIT);
        return;
    }

    int notify_result = cv1_notify_storage(cv1_data_buffer, CV1_BLE_CHUNK_SIZE);
    if (notify_result < 0) {
        return;
    }

    if ((cv1_chunk_count % 50U) == 0U) {
        LOG_DBG("TX chunk @offset=%u", chunk_offset);
    }
    cv1_chunk_count++;

    if (cv1_read_offset < cv1_file_size) {
        k_work_schedule(&cv1_data_work, K_NO_WAIT);
    } else {
        k_work_schedule(&cv1_end_work, K_NO_WAIT);
    }
}

static void cv1_send_end_work_handler(struct k_work *work)
{
    (void)work;

    if (!cv1_storage_active) {
        return;
    }

    uint8_t end_signal[1] = {100};
    int notify_result = cv1_notify_storage(end_signal, 1);
    if (notify_result >= 0) {
        LOG_DBG("TX end marker");
    }

    k_work_cancel_delayable(&cv1_data_work);
    k_work_cancel_delayable(&cv1_end_work);

    cv1_storage_active = false;
    cv1_pusher_should_read = false;
    cv1_reset_stream_state();
    cv1_current_connection = NULL;
}

static void cv1_storage_thread_func(void *arg1, void *arg2, void *arg3)
{
    while (1) {
        if (atomic_get(&delete_request_flag)) {
            uint8_t file_num = atomic_get(&delete_file_num);
            atomic_set(&delete_request_flag, 0);

            int result = cv1_process_delete_request(file_num);
            uint8_t completion_code = (result == 0) ? CV1_DELETE_SUCCESS : (uint8_t)result;
            cv1_send_delete_completion(completion_code);
            reopen_file_after_delete();
        }

        if (atomic_get(&nuke_request_flag)) {
            atomic_set(&nuke_request_flag, 0);

            int result = cv1_process_nuke_request();
            uint8_t completion_code = (result == 0) ? CV1_DELETE_SUCCESS : (uint8_t)result;
            cv1_send_delete_completion(completion_code);
            reopen_file_after_delete();
        }

        k_msleep(20);
    }
}

static void cv1_storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    storage_is_on = true;
    if (value == BT_GATT_CCC_NOTIFY) {
        atomic_set(&cv1_storage_ccc_enabled, 1);
        LOG_DBG("CCC enabled");

        if (cv1_pending.valid) {
            uint8_t pending_cmd = cv1_pending.cmd;
            uint8_t pending_file = cv1_pending.file;
            uint32_t pending_offset = cv1_pending.offset_be;

            cv1_pending.valid = false;

            uint8_t status = cv1_parse_storage_command(pending_cmd,
                                                      pending_file,
                                                      pending_offset,
                                                      true);
            cv1_send_status_code(status);

            if (pending_cmd == CV1_READ_COMMAND && status == 0) {
                cv1_schedule_data_send();
            }
        }
    } else if (value == 0) {
        atomic_set(&cv1_storage_ccc_enabled, 0);
        LOG_DBG("CCC disabled");

        cv1_current_connection = NULL;
        cv1_storage_active = false;
        if (!audio_file_open) {
            reopen_file_after_delete();
        }
    }
}

static ssize_t cv1_storage_read_characteristic(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               void *buf,
                                               uint16_t len,
                                               uint16_t offset)
{
    if (storage_initializing) {
        uint32_t amount[2] = {0, 0};
        return bt_gatt_attr_read(conn, attr, buf, len, offset, amount, 2 * sizeof(uint32_t));
    }

    if (!file_map_initialized) {
        build_file_map();
    }

    uint32_t total_bytes = total_logical_size;
    if (total_bytes == 0) {
        total_bytes = cached_file_size;
    }

    cv1_file_size = total_bytes;

    uint32_t current_offset = cv1_storage_active ? cv1_read_offset : 0;

    uint32_t amount[2] = {0};
    amount[0] = total_bytes;
    amount[1] = current_offset;

    LOG_DBG("Storage list: size=%u, offset=%u", amount[0], amount[1]);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, amount, 2 * sizeof(uint32_t));
}

static uint8_t cv1_parse_storage_command(uint8_t command, uint8_t file_num, uint32_t offset_be, bool replayed)
{
    (void)replayed;

    uint32_t offset = offset_be;

    if (file_num == 0 || file_num > 1) {
        LOG_ERR("CV1: File %d not supported", file_num);
        return CV1_INVALID_FILE_SIZE;
    }

    switch (command) {
        case CV1_READ_COMMAND: {
            if (!file_map_initialized) {
                build_file_map();
            }

            cv1_file_size = total_logical_size;

            if (cv1_file_size == 0) {
                return CV1_ZERO_FILE_SIZE;
            }

            if (offset > cv1_file_size) {
                offset = cv1_file_size;
            }

            cv1_read_offset = offset;
            cv1_storage_active = true;
            cv1_pusher_should_read = true;
            cv1_reset_stream_state();

            LOG_DBG("READ file=%u size=%u offset=%u", file_num, cv1_file_size, cv1_read_offset);
            return 0;
        }

        case CV1_DELETE_COMMAND:
            LOG_DBG("DELETE file %d", file_num);
            atomic_set(&delete_file_num, file_num);
            atomic_set(&delete_request_flag, 1);
            return 0;

        case CV1_NUKE:
            LOG_DBG("NUKE (clear all files)");
            atomic_set(&nuke_request_flag, 1);
            return 0;

        case CV1_STOP_COMMAND:
            LOG_DBG("STOP command");
            cv1_storage_active = false;
            cv1_reset_stream_state();
            return 0;

        case CV1_HEARTBEAT:
            return 0;

        default:
            LOG_ERR("CV1: Unknown command %d", command);
            return CV1_INVALID_COMMAND;
    }
}

static ssize_t cv1_storage_write_handler(struct bt_conn *conn,
                                         const struct bt_gatt_attr *attr,
                                         const void *buf,
                                         uint16_t len,
                                         uint16_t offset,
                                         uint8_t flags)
{

    if (len != 6 && len != 2) {
        LOG_ERR("CV1: Invalid command length %d", len);
        cv1_send_status_code(CV1_INVALID_COMMAND);
        return len;
    }

    const uint8_t *data = (const uint8_t *)buf;
    uint8_t command = data[0];
    uint8_t file_num = data[1];
    uint32_t offset_be = 0;

    if (len == 6) {
        offset_be = ((uint32_t)data[2] << 24) |
                    ((uint32_t)data[3] << 16) |
                    ((uint32_t)data[4] << 8) |
                    ((uint32_t)data[5]);
    }

    cv1_current_connection = conn;

    if (!atomic_get(&cv1_storage_ccc_enabled)) {
        cv1_pending.cmd = command;
        cv1_pending.file = file_num;
        cv1_pending.offset_be = offset_be;
        cv1_pending.valid = true;
        LOG_DBG("Queued pending cmd=%u file=%u", command, file_num);
        return len;
    }

    cv1_pending.valid = false;

    uint8_t result = cv1_parse_storage_command(command, file_num, offset_be, false);
    cv1_send_status_code(result);

    if (command == CV1_READ_COMMAND && result == 0) {
        cv1_schedule_data_send();
    }

    return len;
}

static void cv1_update_cached_file_size(void)
{
    if (!is_mounted) {
        cached_file_size = 0;
        file_num_array[0] = 0;
        file_num_array[1] = 0;
        return;
    }

    storage_initializing = true;

    struct fs_file_t temp_file;
    fs_file_t_init(&temp_file);

    int ret = fs_open(&temp_file, audio_filename, FS_O_READ);
    if (ret == 0) {
        ret = fs_seek(&temp_file, 0, FS_SEEK_END);
        if (ret >= 0) {
            cached_file_size = fs_tell(&temp_file);
            file_num_array[0] = cached_file_size;
            file_num_array[1] = cached_file_size;
            cv1_file_size = cached_file_size;
            LOG_DBG("Found existing audio file with size %u bytes", cached_file_size);
        }
        fs_close(&temp_file);
    } else {
        cached_file_size = 0;
        file_num_array[0] = 0;
        file_num_array[1] = 0;
        cv1_file_size = 0;
        LOG_DBG("No existing audio file found");
    }

    storage_initializing = false;
}

int storage_init(void)
{
    LOG_INF("Storage service initialized");

    k_work_init(&cv1_status_work, cv1_send_status_work_handler);
    k_work_init_delayable(&cv1_data_work, cv1_send_data_work_handler);
    k_work_init_delayable(&cv1_end_work, cv1_send_end_work_handler);

    k_mutex_init(&file_array_mutex);

    k_thread_create(&cv1_storage_thread,
                    cv1_storage_stack,
                    CV1_STORAGE_THREAD_STACK_SIZE,
                    cv1_storage_thread_func,
                    NULL, NULL, NULL,
                    K_PRIO_COOP(10),
                    0, K_NO_WAIT);

    bt_gatt_service_register(&storage_service);
    cv1_update_cached_file_size();

    return 0;
}
#endif
