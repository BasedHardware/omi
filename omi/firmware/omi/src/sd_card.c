#include "lib/core/sd_card.h"

#include <errno.h>
#include <ff.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/fs/fs.h>
#include <zephyr/fs/fs_sys.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/check.h>
#include <zephyr/sys/util.h>

LOG_MODULE_REGISTER(sd_card, CONFIG_LOG_DEFAULT_LEVEL);

#define DISK_DRIVE_NAME "SD"
#define DISK_MOUNT_PT "/SD:"
#define FS_RET_OK 0

static FATFS fat_fs;

static struct fs_mount_t mp = {
    .type = FS_FATFS,
    .fs_data = &fat_fs,
    .flags = FS_MOUNT_FLAG_NO_FORMAT,
    .storage_dev = (void *) DISK_DRIVE_NAME,
    .mnt_point = DISK_MOUNT_PT,
};

static const char *disk_mount_pt = "/SD:/";
static bool is_mounted = false;
static bool sd_enabled = false;

#ifdef CONFIG_OMI_SD_IDLE_TIMEOUT_MS
#define SD_IDLE_TIMEOUT_MS CONFIG_OMI_SD_IDLE_TIMEOUT_MS
#else
#define SD_IDLE_TIMEOUT_MS 1000
#endif

static K_MUTEX_DEFINE(sd_state_lock);

static void sd_idle_powerdown_handler(struct k_work *work);
static K_WORK_DELAYABLE_DEFINE(sd_idle_work, sd_idle_powerdown_handler);

// Get the device pointer for the SDHC SPI slot from the device tree
static const struct device *const sd_dev = DEVICE_DT_GET(DT_NODELABEL(sdhc0));
static const struct gpio_dt_spec sd_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

// Audio file management globals
uint8_t file_count = 0;
uint32_t file_num_array[MAX_AUDIO_FILES];

#define MAX_PATH_LENGTH 32
static char current_full_path[MAX_PATH_LENGTH];
static char read_buffer[MAX_PATH_LENGTH];
static char write_buffer[MAX_PATH_LENGTH];

static int sd_enable_power(bool enable)
{
    int ret = 0;

    if (!device_is_ready(sd_dev)) {
        LOG_ERR("SD host controller is not ready");
        return -ENODEV;
    }

    if (sd_en.port != NULL) {
        int cfg_ret = gpio_pin_configure_dt(&sd_en, GPIO_OUTPUT_INACTIVE);
        if (cfg_ret != 0 && cfg_ret != -EALREADY && cfg_ret != -EBUSY) {
            LOG_ERR("Failed to configure SD enable pin (%d)", cfg_ret);
            return cfg_ret;
        }
    }

    if (enable) {
        if (sd_en.port != NULL) {
            ret = gpio_pin_set_dt(&sd_en, 1);
            if (ret) {
                LOG_ERR("Failed to drive SD enable high (%d)", ret);
                return ret;
            }
        }

        int pm_ret = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_RESUME);
        if (pm_ret != 0 && pm_ret != -ENOTSUP && pm_ret != -EALREADY) {
            LOG_ERR("Failed to resume SD device (%d)", pm_ret);
            if (sd_en.port != NULL) {
                gpio_pin_set_dt(&sd_en, 0);
            }
            return pm_ret;
        }

        sd_enabled = true;
        return 0;
    }

    int pm_ret = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_SUSPEND);
    if (pm_ret != 0 && pm_ret != -ENOTSUP && pm_ret != -EALREADY) {
        LOG_ERR("Failed to suspend SD device (%d)", pm_ret);
        ret = pm_ret;
    }

    if (sd_en.port != NULL) {
        int gpio_ret = gpio_pin_set_dt(&sd_en, 0);
        if (gpio_ret) {
            LOG_ERR("Failed to drive SD enable low (%d)", gpio_ret);
            if (ret == 0) {
                ret = gpio_ret;
            }
        }
    }

    if (ret == 0) {
        sd_enabled = false;
    }

    return ret;
}

static int sd_unmount(void)
{
    if (!is_mounted) {
        if (sd_enabled) {
            return sd_enable_power(false);
        }
        return 0;
    }

    int ret = fs_unmount(&mp);
    if (ret) {
        LOG_INF("Disk unmount error (%d)", ret);
        return ret;
    }

    LOG_INF("Disk unmounted");
    is_mounted = false;

    ret = sd_enable_power(false);
    if (ret) {
        LOG_ERR("Failed to power down SD card after unmount (%d)", ret);
        return ret;
    }

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

    if (fs_mount(&mp) != FS_RET_OK) {
        LOG_INF("File system not found, creating file system...");
        ret = fs_mkfs(FS_FATFS, (uintptr_t) mp.storage_dev, NULL, 0);
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

    return ret;
}

static int sd_runtime_acquire(void)
{
    int ret = 0;

    k_mutex_lock(&sd_state_lock, K_FOREVER);
    k_work_cancel_delayable(&sd_idle_work);

    if (!sd_enabled || !is_mounted) {
        ret = sd_mount();
    }

    k_mutex_unlock(&sd_state_lock);
    return ret;
}

static void sd_runtime_release(void)
{
    k_mutex_lock(&sd_state_lock, K_FOREVER);

    if (!is_mounted && !sd_enabled) {
        k_mutex_unlock(&sd_state_lock);
        return;
    }

    if (SD_IDLE_TIMEOUT_MS <= 0) {
        int ret = sd_unmount();
        if (ret) {
            LOG_DBG("Failed to power down SD card immediately (%d)", ret);
        }
        k_mutex_unlock(&sd_state_lock);
        return;
    }

    k_work_reschedule(&sd_idle_work, K_MSEC(SD_IDLE_TIMEOUT_MS));
    k_mutex_unlock(&sd_state_lock);
}

static void sd_idle_powerdown_handler(struct k_work *work)
{
    ARG_UNUSED(work);

    k_mutex_lock(&sd_state_lock, K_FOREVER);

    if (!is_mounted && !sd_enabled) {
        k_mutex_unlock(&sd_state_lock);
        return;
    }

    int ret = sd_unmount();
    if (ret && ret != -ENODEV) {
        LOG_DBG("Idle power-down skipped (%d)", ret);
    }

    k_mutex_unlock(&sd_state_lock);
}

static int get_file_contents(struct fs_dir_t *zdp, struct fs_dirent *entry)
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
        if (count >= MAX_AUDIO_FILES) {
            LOG_ERR("Too many audio files found, max supported is %d", MAX_AUDIO_FILES);
            break;
        }
        file_num_array[count] = entry->size;
        LOG_INF("file numarray %d %d ", count, file_num_array[count]);
        LOG_INF("file name is %s ", entry->name);
        count++;
    }
    return count;
}

int app_sd_init(void)
{
    int ret = sd_runtime_acquire();
    if (ret != 0) {
        return ret;
    }

    bool dir_opened = false;
    struct fs_dir_t audio_dir_entry;
    fs_dir_t_init(&audio_dir_entry);

    LOG_INF("SD card module initialized (Device: %s)", sd_dev->name);

    // Initialize audio file management
    ret = fs_mkdir("/SD:/audio");
    if (ret == FR_OK) {
        LOG_INF("audio directory created successfully");
        initialize_audio_file(1);
    } else if (ret == FR_EXIST) {
        LOG_INF("audio directory already exists");
    } else if (ret) {
        LOG_INF("audio directory creation failed: %d", ret);
    }

    // Scan existing audio files
    int err = fs_opendir(&audio_dir_entry, "/SD:/audio");
    if (err) {
        LOG_ERR("error while opening directory %d", err);
        ret = err;
        goto out;
    }
    dir_opened = true;
    LOG_INF("result of opendir: %d", err);

    initialize_audio_file(1);
    struct fs_dirent file_count_entry;
    int found_files = get_file_contents(&audio_dir_entry, &file_count_entry);
    if (found_files < 0) {
        LOG_ERR("error getting file count");
        ret = -EIO;
        goto out;
    }

    // If files exist but don't match our naming scheme, start fresh
    if (found_files > 0) {
        LOG_WRN("Found %d existing files, but using fresh file system", found_files);
    }
    file_count = 1;

    LOG_INF("new num files: %d", file_count);

    ret = move_write_pointer(file_count);
    if (ret) {
        LOG_ERR("error while moving the write pointer");
        goto out;
    }

    ret = move_read_pointer(file_count);
    if (ret) {
        LOG_ERR("error while moving the reader pointer");
        goto out;
    }
    LOG_INF("file count: %d", file_count);

    // Check if the info file exists, if not create it
    struct fs_dirent info_file_entry;
    const char *info_path = "/SD:/info.txt";
    ret = fs_stat(info_path, &info_file_entry);
    if (ret) {
        ret = create_file("info.txt");
        if (!ret) {
            save_offset(0);
        }
        LOG_INF("result of info.txt creation: %d ", ret);
    }
    LOG_INF("result of check: %d", ret);

    ret = 0;

out:
    if (dir_opened) {
        fs_closedir(&audio_dir_entry);
    }
    sd_runtime_release();
    return ret;
}

char *generate_new_audio_header(uint8_t num)
{
    if (num > 99)
        return NULL;
    char *ptr_ = k_malloc(14);
    if (ptr_ == NULL) {
        return NULL;
    }
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

int create_file(const char *file_path)
{
    int ret = sd_runtime_acquire();
    if (ret) {
        return ret;
    }

    ret = 0;
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, file_path);
    struct fs_file_t data_file;
    fs_file_t_init(&data_file);
    ret = fs_open(&data_file, current_full_path, FS_O_WRITE | FS_O_CREATE);
    if (ret) {
        LOG_ERR("File creation failed %d", ret);
        ret = -2;
        goto out;
    }
    fs_close(&data_file);
    ret = 0;

out:
    sd_runtime_release();
    return ret;
}

int initialize_audio_file(uint8_t num)
{
    char *header = generate_new_audio_header(num);
    if (header == NULL) {
        return -1;
    }
    int ret = create_file(header);
    k_free(header);
    return ret;
}

uint32_t get_file_size(uint8_t num)
{
    uint32_t size = 0;
    int ret = sd_runtime_acquire();
    if (ret) {
        LOG_ERR("Failed to prepare SD card for get_file_size (%d)", ret);
        return 0;
    }

    char *ptr = generate_new_audio_header(num);
    if (ptr == NULL) {
        sd_runtime_release();
        return 0;
    }
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, ptr);
    k_free(ptr);
    struct fs_dirent entry;
    int res = fs_stat(current_full_path, &entry);
    if (res) {
        LOG_ERR("invalid file in get file size");
        goto out;
    }
    size = (uint32_t) entry.size;

out:
    sd_runtime_release();
    return size;
}

int move_read_pointer(uint8_t num)
{
    int status = sd_runtime_acquire();
    if (status) {
        LOG_ERR("Failed to prepare SD card for move_read_pointer (%d)", status);
        return status;
    }

    char *read_ptr = generate_new_audio_header(num);
    if (read_ptr == NULL) {
        sd_runtime_release();
        return -1;
    }
    snprintf(read_buffer, sizeof(read_buffer), "%s%s", disk_mount_pt, read_ptr);
    k_free(read_ptr);
    struct fs_dirent entry;
    int res = fs_stat(read_buffer, &entry);
    if (res) {
        LOG_ERR("invalid file in move read ptr");
        status = -1;
    }
    sd_runtime_release();
    return status;
}

int move_write_pointer(uint8_t num)
{
    int status = sd_runtime_acquire();
    if (status) {
        LOG_ERR("Failed to prepare SD card for move_write_pointer (%d)", status);
        return status;
    }

    char *write_ptr = generate_new_audio_header(num);
    if (write_ptr == NULL) {
        sd_runtime_release();
        return -1;
    }
    snprintf(write_buffer, sizeof(write_buffer), "%s%s", disk_mount_pt, write_ptr);
    k_free(write_ptr);
    struct fs_dirent entry;
    int res = fs_stat(write_buffer, &entry);
    if (res) {
        LOG_ERR("invalid file in move write pointer");
        status = -1;
    }
    sd_runtime_release();
    return status;
}

int read_audio_data(uint8_t *buf, int amount, int offset)
{
    int rc = sd_runtime_acquire();
    if (rc) {
        return rc;
    }

    struct fs_file_t read_file;
    fs_file_t_init(&read_file);
    uint8_t *temp_ptr = buf;
    bool file_open = false;

    rc = fs_open(&read_file, read_buffer, FS_O_READ | FS_O_RDWR);
    if (rc < 0) {
        LOG_ERR("Failed to open file for reading: %d", rc);
        goto out;
    }
    file_open = true;
    rc = fs_seek(&read_file, offset, FS_SEEK_SET);
    if (rc < 0) {
        LOG_ERR("Failed to seek file: %d", rc);
        goto out;
    }
    rc = fs_read(&read_file, temp_ptr, amount);
    if (rc < 0) {
        LOG_ERR("Failed to read audio data: %d", rc);
    }

out:
    if (file_open) {
        fs_close(&read_file);
    }
    sd_runtime_release();
    return rc;
}

int write_to_file(uint8_t *data, uint32_t length)
{
    int ret = sd_runtime_acquire();
    if (ret) {
        return ret;
    }

    struct fs_file_t write_file;
    fs_file_t_init(&write_file);
    uint8_t *write_ptr = data;
    bool file_open = false;

    ret = fs_open(&write_file, write_buffer, FS_O_WRITE | FS_O_APPEND);
    if (ret < 0) {
        LOG_ERR("Failed to open file for writing: %d", ret);
        goto out;
    }
    file_open = true;
    ret = fs_write(&write_file, write_ptr, length);
    if (ret < 0) {
        LOG_ERR("Failed to write audio data: %d", ret);
    }

out:
    if (file_open) {
        fs_close(&write_file);
    }
    sd_runtime_release();
    return ret;
}

int clear_audio_file(uint8_t num)
{
    int status = sd_runtime_acquire();
    if (status) {
        return status;
    }

    char *clear_header = generate_new_audio_header(num);
    if (clear_header == NULL) {
        sd_runtime_release();
        return -1;
    }
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, clear_header);
    k_free(clear_header);
    int res = fs_unlink(current_full_path);
    if (res) {
        LOG_ERR("error deleting file");
        status = -1;
        goto out;
    }

    char *create_file_header = generate_new_audio_header(num);
    if (create_file_header == NULL) {
        status = -1;
        goto out;
    }
    k_msleep(10);
    res = create_file(create_file_header);
    k_free(create_file_header);
    if (res) {
        LOG_ERR("error creating file");
        status = -1;
    }

out:
    sd_runtime_release();
    return status;
}

static int delete_audio_file(uint8_t num)
{
    int status = sd_runtime_acquire();
    if (status) {
        return status;
    }

    char *ptr = generate_new_audio_header(num);
    if (ptr == NULL) {
        sd_runtime_release();
        return -1;
    }
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, ptr);
    k_free(ptr);
    int res = fs_unlink(current_full_path);
    if (res) {
        LOG_PRINTK("error deleting file in delete\n");
        status = -1;
    }
    sd_runtime_release();
    return status;
}

int clear_audio_directory(void)
{
    int status = sd_runtime_acquire();
    if (status) {
        return status;
    }

    if (file_count == 1) {
        sd_runtime_release();
        return 0;
    }

    int res = 0;
    for (uint8_t i = file_count; i > 0; i--) {
        res = delete_audio_file(i);
        k_msleep(10);
        if (res) {
            LOG_PRINTK("error on %d\n", i);
            status = -1;
            goto out;
        }
    }
    res = fs_unlink("/SD:/audio");
    if (res) {
        LOG_ERR("error deleting directory");
        status = -1;
        goto out;
    }
    res = fs_mkdir("/SD:/audio");
    if (res) {
        LOG_ERR("failed to make directory");
        status = -1;
        goto out;
    }
    res = create_file("audio/a01.txt");
    if (res) {
        LOG_ERR("failed to make new file in directory files");
        status = -1;
        goto out;
    }
    LOG_INF("done with clearing");

    file_count = 1;
    move_write_pointer(1);
    status = 0;

out:
    sd_runtime_release();
    return status;
}

int save_offset(uint32_t offset)
{
    int res = sd_runtime_acquire();
    if (res) {
        return res;
    }

    uint8_t buf[4] = {offset & 0xFF, (offset >> 8) & 0xFF, (offset >> 16) & 0xFF, (offset >> 24) & 0xFF};

    struct fs_file_t write_file;
    fs_file_t_init(&write_file);
    bool file_open = false;

    res = fs_open(&write_file, "/SD:/info.txt", FS_O_WRITE | FS_O_CREATE);
    if (res) {
        LOG_ERR("error opening file %d", res);
        res = -1;
        goto out;
    }
    file_open = true;
    res = fs_write(&write_file, &buf, 4);
    if (res < 0) {
        LOG_ERR("error writing file %d", res);
        res = -1;
        goto out;
    }
    res = 0;

out:
    if (file_open) {
        fs_close(&write_file);
    }
    sd_runtime_release();
    return res;
}

int get_offset(void)
{
    int rc = sd_runtime_acquire();
    if (rc) {
        return rc;
    }

    uint8_t buf[4];
    struct fs_file_t read_file;
    fs_file_t_init(&read_file);
    bool file_open = false;

    rc = fs_open(&read_file, "/SD:/info.txt", FS_O_READ | FS_O_RDWR);
    if (rc < 0) {
        LOG_ERR("error opening file %d", rc);
        rc = -1;
        goto out;
    }
    file_open = true;
    rc = fs_seek(&read_file, 0, FS_SEEK_SET);
    if (rc < 0) {
        LOG_ERR("error seeking file %d", rc);
        rc = -1;
        goto out;
    }
    rc = fs_read(&read_file, &buf, 4);
    if (rc < 0) {
        LOG_ERR("error reading file %d", rc);
        rc = -1;
        goto out;
    }
    fs_close(&read_file);
    file_open = false;
    uint32_t *offset_ptr = (uint32_t *) buf;
    LOG_INF("get offset is %d", offset_ptr[0]);
    rc = (int) offset_ptr[0];

out:
    if (file_open) {
        fs_close(&read_file);
    }
    sd_runtime_release();
    return rc;
}

int app_sd_off(void)
{
    int ret = 0;

    k_mutex_lock(&sd_state_lock, K_FOREVER);
    k_work_cancel_delayable(&sd_idle_work);

    if (is_mounted || sd_enabled) {
        ret = sd_unmount();
    }

    k_mutex_unlock(&sd_state_lock);
    return ret;
}

bool is_sd_on(void)
{
    return sd_enabled;
}
