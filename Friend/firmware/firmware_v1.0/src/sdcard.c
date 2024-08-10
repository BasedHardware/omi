#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/fs/fs.h>
#include "lib/fatfs/include/ff.h"
#include "sdcard.h"
#include <zephyr/logging/log.h>

#define SD_MOUNT_POINT "/SD:"

LOG_MODULE_REGISTER(sdcard, CONFIG_LOG_DEFAULT_LEVEL);

static FATFS fat_fs;
static struct fs_mount_t mp = {
    .type = FS_FATFS,
    .fs_data = &fat_fs,
};

bool sd_card_mounted = false;

int mount_sd_card(void)
{
    if (disk_access_init("SD") != 0) {
        LOG_ERR("Failed to initialize SD card");
        return -1;
    }

    mp.mnt_point = SD_MOUNT_POINT;
    int ret = fs_mount(&mp);
    if (ret == 0) {
        sd_card_mounted = true;
        LOG_INF("SD card mounted successfully");
        return 0;
    } else {
        LOG_ERR("Failed to mount SD card: %d", ret);
        return -1;
    }
}

int create_file(const char *file_path)
{
    char full_path[MAX_PATH_SIZE];
    struct fs_file_t file;

    snprintf(full_path, sizeof(full_path), "%s/%s", SD_MOUNT_POINT, file_path);

    fs_file_t_init(&file);
    int ret = fs_open(&file, full_path, FS_O_CREATE | FS_O_WRITE);
    if (ret) {
        LOG_ERR("Failed to create file %s: %d", full_path, ret);
        return -1;
    }

    fs_close(&file);
    return 0;
}

int write_file(const char *file_path, const uint8_t *data, size_t length, bool append)
{
    char full_path[MAX_PATH_SIZE];
    struct fs_file_t file;

    snprintf(full_path, sizeof(full_path), "%s/%s", SD_MOUNT_POINT, file_path);

    fs_file_t_init(&file);
    int flags = FS_O_WRITE;
    if (append) {
        flags |= FS_O_APPEND;
    }
    int ret = fs_open(&file, full_path, flags);
    if (ret) {
        LOG_ERR("Failed to open file %s for writing: %d", full_path, ret);
        return -1;
    }

    ret = fs_write(&file, data, length);
    if (ret < 0) {
        LOG_ERR("Failed to write to file %s: %d", full_path, ret);
        fs_close(&file);
        return -1;
    }

    fs_close(&file);
    return 0;
}

int read_file(const char *file_path, uint8_t *buffer, size_t buffer_size, size_t *bytes_read)
{
    char full_path[MAX_PATH_SIZE];
    struct fs_file_t file;

    snprintf(full_path, sizeof(full_path), "%s/%s", SD_MOUNT_POINT, file_path);

    fs_file_t_init(&file);
    int ret = fs_open(&file, full_path, FS_O_READ);
    if (ret) {
        LOG_ERR("Failed to open file %s for reading: %d", full_path, ret);
        return -1;
    }

    ret = fs_read(&file, buffer, buffer_size);
    if (ret < 0) {
        LOG_ERR("Failed to read file %s: %d", full_path, ret);
        fs_close(&file);
        return -1;
    }

    *bytes_read = ret;
    fs_close(&file);
    return 0;
}

int delete_file(const char *file_path)
{
    char full_path[MAX_PATH_SIZE];
    snprintf(full_path, sizeof(full_path), "%s/%s", SD_MOUNT_POINT, file_path);

    int ret = fs_unlink(full_path);
    if (ret) {
        LOG_ERR("Failed to delete file %s: %d", full_path, ret);
        return -1;
    }

    return 0;
}
