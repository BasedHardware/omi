#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/pm/device.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/fs/fs.h>
#include <zephyr/fs/ext2.h>
#include <zephyr/logging/log.h>

#include "sd_card.h"

LOG_MODULE_REGISTER(sd_card, CONFIG_LOG_DEFAULT_LEVEL);

#define DISK_DRIVE_NAME "SDMMC"
#define DISK_MOUNT_PT "/ext"
#define FS_RET_OK 0

static struct fs_mount_t mp = {
    .type = FS_EXT2,
    .flags = FS_MOUNT_FLAG_NO_FORMAT,
    .storage_dev = (void *)DISK_DRIVE_NAME,
    .mnt_point = "/ext",
};

static const char *disk_mount_pt = DISK_MOUNT_PT;
static bool is_mounted = false;

// Get the device pointer for the SDHC SPI slot from the device tree
static const struct device *const sd_dev = DEVICE_DT_GET(DT_NODELABEL(sdhc0));
static const struct gpio_dt_spec sd_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

static int sd_enable_power(bool enable)
{
    int ret;
    gpio_pin_configure_dt(&sd_en, GPIO_OUTPUT);
    if (enable)
    {
        ret = gpio_pin_set_dt(&sd_en, 1);
        pm_device_action_run(sd_dev, PM_DEVICE_ACTION_RESUME);
    }
    else
    {
        ret = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_SUSPEND);
        // gpio_pin_set_dt(&sd_en,    0);
    }
    return ret;
}

static int sd_unmount()
{
    int ret;
    ret = fs_unmount(&mp);
    if (ret)
    {
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
    do
    {
        static const char *disk_pdrv = DISK_DRIVE_NAME;
        uint64_t memory_size_mb;
        uint32_t block_count;
        uint32_t block_size;

        ret = sd_enable_power(true);
        if (ret < 0) {
            LOG_ERR("Failed to power on SD card (%d)", ret);
            return ret;
        }

        if (disk_access_ioctl(disk_pdrv,
                              DISK_IOCTL_CTRL_INIT, NULL) != 0)
        {
            LOG_ERR("Storage init ERROR!");
            break;
        }

        if (disk_access_ioctl(disk_pdrv,
                              DISK_IOCTL_GET_SECTOR_COUNT, &block_count))
        {
            LOG_ERR("Unable to get sector count");
            break;
        }
        LOG_INF("Block count %u", block_count);

        if (disk_access_ioctl(disk_pdrv,
                              DISK_IOCTL_GET_SECTOR_SIZE, &block_size))
        {
            LOG_ERR("Unable to get sector size");
            break;
        }
        LOG_INF("Sector size %u", block_size);

        memory_size_mb = (uint64_t)block_count * block_size;
        LOG_INF("Memory Size(MB) %u", (uint32_t)(memory_size_mb >> 20));

        if (disk_access_ioctl(disk_pdrv,
                              DISK_IOCTL_CTRL_DEINIT, NULL) != 0)
        {
            LOG_ERR("Storage deinit ERROR!");
            break;
        }
    } while (0);
    mp.mnt_point = disk_mount_pt;

    if (is_mounted)
    {
        LOG_INF("Disk already mounted.");
        return 0;
    }

    if (fs_mount(&mp) != FS_RET_OK)
    {
        LOG_INF("File system not found, creating file system...");
        ret = fs_mkfs(FS_EXT2, (uintptr_t)mp.storage_dev, NULL, 0);
        if (ret != 0)
        {
            LOG_ERR("Error formatting filesystem [%d]", ret);
            sd_enable_power(false);
            return ret;
        }

        ret = fs_mount(&mp);
        if (ret != FS_RET_OK)
        {
            LOG_INF("Error mounting disk %d.", ret);
            sd_enable_power(false);
            return ret;
        }
    }

    LOG_INF("Disk mounted.");
    is_mounted = true;

    return ret;
}

int app_sd_init(void)
{
    LOG_INF("TODO: SD card module initialized (Device: %s)", sd_dev->name);
    return 0;
}

int app_sd_off(void)
{
    sd_mount();
    sd_unmount();
    return 0;
}
