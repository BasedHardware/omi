#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/fs/fs.h>
#include "sdcard.h"

LOG_MODULE_REGISTER(sdcard, CONFIG_LOG_DEFAULT_LEVEL);

#define SD_MOUNT_POINT "/SD:"

static FATFS fat_fs;
static bool sd_mounted = false;

int mount_sd_card(void)
{
    static const char *disk_pdrv = "SD";
    uint64_t memory_size_mb;
    uint32_t block_count;
    uint32_t block_size;

    if (sd_mounted) {
        LOG_INF("SD card already mounted");
        return 0;
    }

    if (disk_access_init(disk_pdrv) != 0) {
        LOG_ERR("Storage init ERROR!");
        return -EIO;
    }

    if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_GET_SECTOR_COUNT, &block_count)) {
        LOG_ERR("Unable to get sector count");
        return -EIO;
    }
    LOG_INF("Block count %u", block_count);

    if (disk_access_ioctl(disk_pdrv, DISK_IOCTL_GET_SECTOR_SIZE, &block_size)) {
        LOG_ERR("Unable to get sector size");
        return -EIO;
    }
    LOG_INF("Sector size %u", block_size);

    memory_size_mb = (uint64_t)block_count * block_size;
    LOG_INF("Memory Size(MB) %u", (uint32_t)(memory_size_mb >> 20));

    static const FATFS_MKFS_PARAM mkfs_opts = {
        .fm_type = FM_ANY,
        .n_fat = 1,
        .align = 0,
        .n_root = 512,
        .au_size = 0
    };

    FRESULT res = f_mount(&fat_fs, SD_MOUNT_POINT, 1);
    if (res != FR_OK) {
        LOG_INF("Formatting SD card...");
        res = f_mkfs(SD_MOUNT_POINT, &mkfs_opts, NULL, 0);
        if (res != FR_OK) {
            LOG_ERR("Error formatting SD card: %d", res);
            return -EIO;
        }
        LOG_INF("SD card formatted successfully");

        res = f_mount(&fat_fs, SD_MOUNT_POINT, 1);
    }

    if (res == FR_OK) {
        sd_mounted = true;
        LOG_INF("SD card mounted successfully");
        return 0;
    } else {
        LOG_ERR("Error mounting SD card: %d", res);
        return -EIO;
    }
}

int create_directory(const char *dir_path)
{
    FRESULT res = f_mkdir(dir_path);
    if (res == FR_OK || res == FR_EXIST) {
        return 0;
    } else {
        LOG_ERR("Error creating directory: %d", res);
        return -EIO;
    }
}

int create_file(const char *file_path)
{
    FIL file;
    FRESULT res = f_open(&file, file_path, FA_WRITE | FA_CREATE_ALWAYS);
    if (res == FR_OK) {
        f_close(&file);
        return 0;
    } else {
        LOG_ERR("Error creating file: %d", res);
        return -EIO;
    }
}

int write_file(const char *file_path, const uint8_t *data, size_t length, bool append)
{
    FIL file;
    FRESULT res;
    UINT bw;

    res = f_open(&file, file_path, append ? (FA_WRITE | FA_OPEN_APPEND) : (FA_WRITE | FA_CREATE_ALWAYS));
    if (res != FR_OK) {
        LOG_ERR("Error opening file for writing: %d", res);
        return -EIO;
    }

    res = f_write(&file, data, length, &bw);
    f_close(&file);

    if (res != FR_OK) {
        LOG_ERR("Error writing to file: %d", res);
        return -EIO;
    }

    if (bw != length) {
        LOG_ERR("Error: wrote %u bytes instead of %u", bw, length);
        return -EIO;
    }

    return 0;
}

int read_file(const char *file_path, uint8_t *buffer, size_t buffer_size, size_t *bytes_read)
{
    FIL file;
    FRESULT res;
    UINT br;

    res = f_open(&file, file_path, FA_READ);
    if (res != FR_OK) {
        LOG_ERR("Error opening file for reading: %d", res);
        return -EIO;
    }

    res = f_read(&file, buffer, buffer_size, &br);
    f_close(&file);

    if (res != FR_OK) {
        LOG_ERR("Error reading file: %d", res);
        return -EIO;
    }

    *bytes_read = br;
    return 0;
}

int delete_file(const char *file_path)
{
    FRESULT res = f_unlink(file_path);
    if (res == FR_OK) {
        return 0;
    } else {
        LOG_ERR("Error deleting file: %d", res);
        return -EIO;
    }
}
