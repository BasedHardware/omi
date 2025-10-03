#include "lib/dk2/sd_card.h"

#include <ff.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/fs/fs.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device.h>
#include <zephyr/storage/disk_access.h>

LOG_MODULE_REGISTER(sd_card, CONFIG_LOG_DEFAULT_LEVEL);

#define DISK_DRIVE_NAME "SD"
#define DISK_MOUNT_PT "/SD:"
#define METADATA_FILE_PATH "/SD:/audio_metadata.bin"
#define FS_RET_OK 0

static FATFS fat_fs;

static struct fs_mount_t mp = {
    .type = FS_FATFS,
    .fs_data = &fat_fs,
    .storage_dev = (void *) DISK_DRIVE_NAME,
    .mnt_point = DISK_MOUNT_PT,
};

static const char *disk_mount_pt = DISK_MOUNT_PT;
static bool is_mounted = false;
static bool is_writable = false;

// Current write file tracking
static uint8_t current_write_file = 1;
static uint32_t current_file_size = 0;
static uint32_t current_file_start_time_sec = 0;

// File handle for the currently open audio file
static struct fs_file_t current_audio_file;
static bool is_audio_file_open = false;
static uint8_t open_file_num = 0;

// Mutex for thread-safe SD card access
static K_MUTEX_DEFINE(sd_mutex);

// Get the device pointer for the SDHC SPI slot from the device tree
static const struct device *const sd_dev = DEVICE_DT_GET(DT_NODELABEL(sdhc0));
static const struct gpio_dt_spec sd_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

static int sd_enable_power(bool enable)
{
    int ret;
    gpio_pin_configure_dt(&sd_en, GPIO_OUTPUT);
    if (enable) {
        ret = gpio_pin_set_dt(&sd_en, 1);
        if (ret < 0) {
            LOG_ERR("Failed to set SD card power pin: %d", ret);
            return ret;
        }
        // PM operations are optional - some drivers don't support them
        int pm_ret = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_RESUME);
        if (pm_ret < 0 && pm_ret != -ENOSYS) {
            LOG_WRN("PM resume not supported or failed: %d (continuing anyway)", pm_ret);
        }
        // Give SD card time to power up and stabilize
        k_msleep(100);
    } else {
        // PM operations are optional - some drivers don't support them
        int pm_ret = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_SUSPEND);
        if (pm_ret < 0 && pm_ret != -ENOSYS) {
            LOG_WRN("PM suspend not supported or failed: %d (continuing anyway)", pm_ret);
        }
        ret = gpio_pin_set_dt(&sd_en, 0);
        if (ret < 0) {
            LOG_ERR("Failed to clear SD card power pin: %d", ret);
            return ret;
        }
    }
    return 0;
}

static int sd_unmount(void)
{
    int ret;
    ret = fs_unmount(&mp);
    if (ret) {
        LOG_INF("Disk unmounted error (%d)", ret);
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

    if (is_mounted) {
        LOG_INF("Disk already mounted.");
        return 0;
    }

    // Check if SD card device is ready
    if (!device_is_ready(sd_dev)) {
        LOG_ERR("SD card device not ready");
        return -ENODEV;
    }

    // Power on SD card (bootloader powered it down)
    ret = sd_enable_power(true);
    if (ret < 0) {
        LOG_ERR("Failed to power on SD card (%d)", ret);
        return ret;
    }

    // Initialize disk with retry logic like devkit
    static const char *disk_pdrv = DISK_DRIVE_NAME;
    ret = disk_access_init(disk_pdrv);
    LOG_INF("disk_access_init: %d", ret);
    if (ret != 0) {
        LOG_INF("Init failed, retrying after delay...");
        k_msleep(1000);
        ret = disk_access_init(disk_pdrv);
        if (ret != 0) {
            LOG_ERR("Storage init failed: %d", ret);
            sd_enable_power(false);
            return ret;
        }
    }

    // Get disk information
    uint32_t block_count;
    uint32_t block_size;
    if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_GET_SECTOR_COUNT, &block_count) == 0) {
        LOG_INF("Block count %u", block_count);
    }

    if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_GET_SECTOR_SIZE, &block_size) == 0) {
        LOG_INF("Sector size %u", block_size);
        uint64_t memory_size_mb = (uint64_t) block_count * block_size;
        LOG_INF("Memory Size(MB) %u", (uint32_t) (memory_size_mb >> 20));
    }

    // Keep disk initialized and try to mount
    mp.mnt_point = disk_mount_pt;
    ret = fs_mount(&mp);
    if (ret != FS_RET_OK) {
        LOG_INF("Mount failed (possibly EXT2 format), formatting to FATFS...");
        ret = fs_mkfs(FS_FATFS, (uintptr_t) mp.storage_dev, NULL, 0);
        if (ret != 0) {
            LOG_ERR("Error formatting filesystem [%d]", ret);
            sd_enable_power(false);
            return ret;
        }

        ret = fs_mount(&mp);
        if (ret != FS_RET_OK) {
            LOG_ERR("Error mounting disk [%d]", ret);
            sd_enable_power(false);
            return ret;
        }
    }

    LOG_INF("Disk mounted at %s", mp.mnt_point);
    is_mounted = true;

    // Test if the card is writable by writing a small test file
    const char *test_path = "/SD:/write_test.tmp";
    LOG_DBG("Testing SD card write capability with: %s", test_path);
    struct fs_file_t test_file;
    fs_file_t_init(&test_file);

    uint8_t test_data[8] = {0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA};

    ret = fs_open(&test_file, test_path, FS_O_CREATE | FS_O_WRITE);
    if (ret == 0) {
        ret = fs_write(&test_file, test_data, sizeof(test_data));
        fs_close(&test_file);

        if (ret >= 0) {
            // Successfully wrote to the file
            is_writable = true;
            LOG_INF("SD card verified as writable");

            // Clean up the test file
            fs_unlink(test_path);
            ret = 0;
        } else {
            LOG_ERR("SD card not writable: write error %d", ret);
            is_writable = false;
        }
    } else {
        LOG_ERR("SD card not writable: open error %d", ret);
        is_writable = false;
    }

    return ret;
}

static int ensure_audio_directory(void)
{
    struct fs_dirent entry;
    int ret = fs_stat(AUDIO_FILE_PATH_PREFIX, &entry);

    if (ret != 0) {
        LOG_INF("Audio directory doesn't exist, creating: %s", AUDIO_FILE_PATH_PREFIX);
        ret = fs_mkdir(AUDIO_FILE_PATH_PREFIX);
        if (ret != 0 && ret != -EEXIST) {
            LOG_ERR("Failed to create audio directory %s: %d", AUDIO_FILE_PATH_PREFIX, ret);
            return ret;
        }
        LOG_INF("Audio directory created successfully");
    } else {
        LOG_INF("Audio directory already exists");
    }
    return 0;
}

static void get_audio_file_path(uint8_t file_num, char *path_buf, size_t buf_size)
{
    snprintf(path_buf, buf_size, "%s/audio_%03d.bin", AUDIO_FILE_PATH_PREFIX, file_num);
}

static int save_metadata(void)
{
    struct fs_file_t file;
    fs_file_t_init(&file);

    int ret = fs_open(&file, METADATA_FILE_PATH, FS_O_CREATE | FS_O_WRITE | FS_O_TRUNC);
    if (ret < 0) {
        LOG_ERR("Failed to open metadata file: %d", ret);
        return ret;
    }

    // Write current file tracking info
    struct {
        uint8_t current_file;
        uint32_t current_size;
        uint32_t current_start_time;
    } metadata = {
        .current_file = current_write_file,
        .current_size = current_file_size,
        .current_start_time = current_file_start_time_sec,
    };

    ret = fs_write(&file, &metadata, sizeof(metadata));
    fs_close(&file);

    return ret < 0 ? ret : 0;
}

static int load_metadata(void)
{
    struct fs_file_t file;
    fs_file_t_init(&file);

    int ret = fs_open(&file, METADATA_FILE_PATH, FS_O_READ);
    if (ret < 0) {
        // File doesn't exist, use defaults
        LOG_INF("Metadata file not found, using defaults");
        current_write_file = 1;
        current_file_size = 0;
        current_file_start_time_sec = 0;
        return 0;
    }

    struct {
        uint8_t current_file;
        uint32_t current_size;
        uint32_t current_start_time;
    } metadata;

    ret = fs_read(&file, &metadata, sizeof(metadata));
    fs_close(&file);

    // If read failed or incomplete, reset to defaults instead of failing
    if (ret != sizeof(metadata)) {
        LOG_WRN("Metadata file corrupted (read %d bytes, expected %d), resetting to defaults", ret, sizeof(metadata));
        current_write_file = 1;
        current_file_size = 0;
        current_file_start_time_sec = 0;
        // Delete corrupted metadata file
        fs_unlink(METADATA_FILE_PATH);
        return 0;
    }

    // Validate metadata values
    if (metadata.current_file == 0 || metadata.current_file > MAX_AUDIO_FILES) {
        LOG_WRN("Invalid metadata: file_num=%d, resetting to defaults", metadata.current_file);
        current_write_file = 1;
        current_file_size = 0;
        current_file_start_time_sec = 0;
        fs_unlink(METADATA_FILE_PATH);
        return 0;
    }

    // Metadata is valid, use it
    current_write_file = metadata.current_file;
    current_file_size = metadata.current_size;
    current_file_start_time_sec = metadata.current_start_time;
    LOG_INF("Loaded metadata: file=%d, size=%u, start_time=%u",
            current_write_file,
            current_file_size,
            current_file_start_time_sec);

    return 0;
}

int app_sd_init(void)
{
    LOG_INF("SD card module initializing (Device: %s)", sd_dev->name);
    return 0;
}

int app_sd_mount(void)
{
    k_mutex_lock(&sd_mutex, K_FOREVER);

    int ret = sd_mount();
    if (ret != 0) {
        k_mutex_unlock(&sd_mutex);
        return ret;
    }

    ret = ensure_audio_directory();
    if (ret != 0) {
        sd_unmount();
        k_mutex_unlock(&sd_mutex);
        return ret;
    }

    ret = load_metadata();

    k_mutex_unlock(&sd_mutex);
    return ret;
}

int app_sd_unmount(void)
{
    k_mutex_lock(&sd_mutex, K_FOREVER);

    if (is_mounted) {
        save_metadata();
        if (is_audio_file_open) {
            fs_close(&current_audio_file);
            is_audio_file_open = false;
        }
    }

    int ret = sd_unmount();
    k_mutex_unlock(&sd_mutex);
    return ret;
}

int app_sd_off(void)
{
    return app_sd_unmount();
}

int app_sd_write_audio(uint8_t *data, uint32_t length, uint32_t current_time_sec)
{
    if (!is_mounted || !is_writable || data == NULL || length == 0) {
        return -EINVAL;
    }

    k_mutex_lock(&sd_mutex, K_FOREVER);

    // Check if we need to rotate to a new file
    if (current_file_size + length > MAX_FILE_SIZE_BYTES) {
        // Close current file if open
        if (is_audio_file_open) {
            fs_close(&current_audio_file);
            is_audio_file_open = false;
        }
        // Save current file metadata
        save_metadata();

        // Move to next file
        current_write_file++;
        if (current_write_file > MAX_AUDIO_FILES) {
            // Wrap around and overwrite oldest file
            current_write_file = 1;
        }

        current_file_size = 0;
        current_file_start_time_sec = current_time_sec;

        LOG_INF("Rotating to new audio file: %d", current_write_file);
    }

    // Open file if not already open or if we switched files
    if (!is_audio_file_open || open_file_num != current_write_file) {
        if (is_audio_file_open) {
            fs_close(&current_audio_file);
            is_audio_file_open = false;
        }

        char file_path[64];
        get_audio_file_path(current_write_file, file_path, sizeof(file_path));

        // Ensure audio directory exists before opening file
        int ret = ensure_audio_directory();
        if (ret < 0) {
            LOG_ERR("Failed to ensure audio directory exists: %d", ret);
            k_mutex_unlock(&sd_mutex);
            return ret;
        }

        LOG_DBG("Opening audio file: %s", file_path);
        fs_file_t_init(&current_audio_file);
        ret = fs_open(&current_audio_file, file_path, FS_O_CREATE | FS_O_WRITE | FS_O_APPEND);
        if (ret < 0) {
            LOG_ERR("Failed to open audio file %s: %d", file_path, ret);

            // Try to verify directory exists
            struct fs_dirent entry;
            int dir_check = fs_stat(AUDIO_FILE_PATH_PREFIX, &entry);
            LOG_ERR("Directory check for %s: %d", AUDIO_FILE_PATH_PREFIX, dir_check);

            k_mutex_unlock(&sd_mutex);
            return ret;
        }
        LOG_INF("Audio file opened successfully: %s", file_path);
        is_audio_file_open = true;
        open_file_num = current_write_file;
    }

    // Write data
    int ret = fs_write(&current_audio_file, data, length);

    if (ret < 0) {
        LOG_ERR("Failed to write to audio file: %d", ret);

        // If we get a no space error, mark the card as not writable
        if (ret == -28) { // -ENOSPC
            LOG_ERR("SD card is full, marking as not writable");
            is_writable = false;
        }

        // Attempt to recover by closing the file
        fs_close(&current_audio_file);
        is_audio_file_open = false;
        k_mutex_unlock(&sd_mutex);
        return ret;
    }

    current_file_size += ret;

    // Save every ~500 writes
    static uint32_t write_count = 0;
    if (++write_count % 500 == 0) {
        int save_ret = save_metadata();
        if (save_ret < 0) {
            LOG_ERR("Failed to save metadata: %d", save_ret);
        }
        fs_sync(&current_audio_file);
    }

    k_mutex_unlock(&sd_mutex);
    return ret;
}

int app_sd_read_audio(uint8_t file_num, uint8_t *buf, uint32_t length, uint32_t offset)
{
    if (!is_mounted || buf == NULL || length == 0 || file_num == 0 || file_num > MAX_AUDIO_FILES) {
        return -EINVAL;
    }

    k_mutex_lock(&sd_mutex, K_FOREVER);

    char file_path[64];
    get_audio_file_path(file_num, file_path, sizeof(file_path));

    struct fs_file_t file;
    fs_file_t_init(&file);

    int ret = fs_open(&file, file_path, FS_O_READ);
    if (ret < 0) {
        k_mutex_unlock(&sd_mutex);
        return ret;
    }

    ret = fs_seek(&file, offset, FS_SEEK_SET);
    if (ret < 0) {
        fs_close(&file);
        k_mutex_unlock(&sd_mutex);
        return ret;
    }

    ret = fs_read(&file, buf, length);
    fs_close(&file);

    k_mutex_unlock(&sd_mutex);
    return ret;
}

int app_sd_get_file_list(struct audio_file_metadata *metadata_array, uint8_t max_count)
{
    if (!is_mounted || metadata_array == NULL || max_count == 0) {
        return -EINVAL;
    }

    k_mutex_lock(&sd_mutex, K_FOREVER);

    uint8_t count = 0;

    for (uint8_t i = 1; i <= MAX_AUDIO_FILES && count < max_count; i++) {
        char file_path[64];
        get_audio_file_path(i, file_path, sizeof(file_path));

        // Special handling for the currently active file
        if (i == current_write_file && current_file_size > 0) {
            // Use in-memory tracking for active file (more reliable than fs_stat)
            metadata_array[count].file_num = i;
            metadata_array[count].file_size = current_file_size;
            metadata_array[count].is_active = true;
            metadata_array[count].start_offset_sec = current_file_start_time_sec;
            metadata_array[count].duration_sec = current_file_size / 5000; // ~5KB/s for opus
            count++;
            LOG_DBG("Found active file %d: size=%u", i, current_file_size);
            continue;
        }

        // For other files, check on disk
        struct fs_dirent entry;
        int ret = fs_stat(file_path, &entry);

        if (ret == 0 && entry.type == FS_DIR_ENTRY_FILE && entry.size > 0) {
            metadata_array[count].file_num = i;
            metadata_array[count].file_size = entry.size;
            metadata_array[count].is_active = false;
            metadata_array[count].start_offset_sec = 0;             // Would need to be calculated from timestamp
            metadata_array[count].duration_sec = entry.size / 5000; // ~5KB/s for opus
            count++;
            LOG_DBG("Found completed file %d: size=%u", i, entry.size);
        } else if (ret != 0 && ret != -ENOENT) {
            LOG_DBG("fs_stat error for %s: %d", file_path, ret);
        }
    }

    k_mutex_unlock(&sd_mutex);

    if (count == 0) {
        LOG_DBG("No files found. Current write file: %d, size: %u, mounted: %d, writable: %d",
                current_write_file,
                current_file_size,
                is_mounted,
                is_writable);
    }

    return count;
}

int app_sd_delete_file(uint8_t file_num)
{
    if (!is_mounted || file_num == 0 || file_num > MAX_AUDIO_FILES) {
        return -EINVAL;
    }

    k_mutex_lock(&sd_mutex, K_FOREVER);

    // If we are deleting the currently open file, close it first
    if (is_audio_file_open && file_num == open_file_num) {
        fs_close(&current_audio_file);
        is_audio_file_open = false;
    }

    char file_path[64];
    get_audio_file_path(file_num, file_path, sizeof(file_path));

    int ret = fs_unlink(file_path);

    // If we deleted the current write file, reset
    if (file_num == current_write_file && ret == 0) {
        current_file_size = 0;
        save_metadata();
    }

    k_mutex_unlock(&sd_mutex);
    return ret;
}

int app_sd_delete_all_files(void)
{
    if (!is_mounted) {
        return -EINVAL;
    }

    k_mutex_lock(&sd_mutex, K_FOREVER);

    // Close any open audio file
    if (is_audio_file_open) {
        fs_close(&current_audio_file);
        is_audio_file_open = false;
    }

    int deleted = 0;
    for (uint8_t i = 1; i <= MAX_AUDIO_FILES; i++) {
        char file_path[64];
        get_audio_file_path(i, file_path, sizeof(file_path));

        if (fs_unlink(file_path) == 0) {
            deleted++;
        }
    }

    // Reset tracking
    current_write_file = 1;
    current_file_size = 0;
    current_file_start_time_sec = 0;
    save_metadata();

    k_mutex_unlock(&sd_mutex);

    LOG_INF("Deleted %d audio files", deleted);
    return 0;
}

bool app_sd_is_ready(void)
{
    return is_mounted;
}

bool app_sd_is_writable(void)
{
    return is_mounted && is_writable;
}
