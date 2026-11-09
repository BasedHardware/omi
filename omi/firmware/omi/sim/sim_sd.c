/* Simulated SD card for the real sd_card.c raw-ring driver.
 *
 * Registers the "SDMMC" disk that sd_card.c opens through the Zephyr
 * disk_access API, plus inert stand-ins for the SD host and SPI bus devices it
 * references. The card's behaviour follows the scenario (sim_power.c):
 *   ok      every operation succeeds
 *   absent  CTRL_INIT always fails (no card / dead socket)
 *   slow    CTRL_INIT fails until sd_ready_ms of uptime, then succeeds
 *   dead    CTRL_INIT succeeds, every read/write fails
 * The image persists in sd.img in the boot's directory, like flash.bin, so
 * ring custody survives simulated power cycles.
 */
#include <errno.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/disk.h>
#include <zephyr/init.h>
#include <zephyr/kernel.h>

#include "posix_native_task.h"
#include "sim_hw.h"
#include "sim_plan.h"

#define SIM_SD_SECTOR 512
#define SIM_SD_SECTORS 4096 /* 2 MiB: a small ring keeps runs fast */

static uint8_t image[SIM_SD_SECTORS][SIM_SD_SECTOR];
static bool image_loaded;
static unsigned int init_calls;
static unsigned int io_errors;
static bool initialized;

unsigned int omi_sim_sd_init_calls(void)
{
    return init_calls;
}

unsigned int omi_sim_sd_io_errors(void)
{
    return io_errors;
}

static bool card_answers(void)
{
    switch (omi_sim_sd_state()) {
    case OMI_SIM_SD_ABSENT:
        return false;
    case OMI_SIM_SD_SLOW:
        return k_uptime_get() >= omi_sim_sd_ready_ms();
    default:
        return true;
    }
}

static int sim_disk_init(struct disk_info *disk)
{
    ARG_UNUSED(disk);
    return 0;
}

static int sim_disk_status(struct disk_info *disk)
{
    ARG_UNUSED(disk);
    return initialized ? DISK_STATUS_OK : DISK_STATUS_UNINIT;
}

static int sim_disk_read(struct disk_info *disk, uint8_t *buf, uint32_t start, uint32_t count)
{
    ARG_UNUSED(disk);
    if (!initialized || omi_sim_sd_state() == OMI_SIM_SD_DEAD || start + count > SIM_SD_SECTORS) {
        io_errors++;
        return -EIO;
    }
    memcpy(buf, image[start], (size_t) count * SIM_SD_SECTOR);
    return 0;
}

static int sim_disk_write(struct disk_info *disk, const uint8_t *buf, uint32_t start, uint32_t count)
{
    ARG_UNUSED(disk);
    if (!initialized || omi_sim_sd_state() == OMI_SIM_SD_DEAD || start + count > SIM_SD_SECTORS) {
        io_errors++;
        return -EIO;
    }
    memcpy(image[start], buf, (size_t) count * SIM_SD_SECTOR);
    return 0;
}

static int sim_disk_ioctl(struct disk_info *disk, uint8_t cmd, void *buf)
{
    ARG_UNUSED(disk);
    switch (cmd) {
    case DISK_IOCTL_CTRL_INIT:
        init_calls++;
        /* A real card takes time to answer CMD0/ACMD41 even when it fails. */
        k_msleep(20);
        if (!card_answers()) {
            return -ETIMEDOUT;
        }
        initialized = true;
        return 0;
    case DISK_IOCTL_CTRL_DEINIT:
        initialized = false;
        return 0;
    case DISK_IOCTL_CTRL_SYNC:
        if (!initialized || omi_sim_sd_state() == OMI_SIM_SD_DEAD) {
            io_errors++;
            return -EIO;
        }
        return 0;
    case DISK_IOCTL_GET_SECTOR_COUNT:
        *(uint32_t *) buf = SIM_SD_SECTORS;
        return 0;
    case DISK_IOCTL_GET_SECTOR_SIZE:
        *(uint32_t *) buf = SIM_SD_SECTOR;
        return 0;
    case DISK_IOCTL_GET_ERASE_BLOCK_SZ:
        *(uint32_t *) buf = 1;
        return 0;
    default:
        return -EINVAL;
    }
}

static const struct disk_operations sim_disk_ops = {
    .init = sim_disk_init,
    .status = sim_disk_status,
    .read = sim_disk_read,
    .write = sim_disk_write,
    .ioctl = sim_disk_ioctl,
};

static struct disk_info sim_disk = {
    .name = "SDMMC",
    .ops = &sim_disk_ops,
};

static int sim_sd_register(void)
{
    image_loaded = omi_sim_host_load_file("sd.img", image, sizeof(image)) == 0;
    return disk_access_register(&sim_disk);
}
SYS_INIT(sim_sd_register, POST_KERNEL, 98);

static void sim_sd_save(void)
{
    (void) omi_sim_host_save_file("sd.img", image, sizeof(image));
}
NATIVE_TASK(sim_sd_save, ON_EXIT, 1);

/* Inert stand-ins for &sdhc0 and &spi3: sd_card.c only power-manages them. */
#define DT_DRV_COMPAT omi_sim_dummy_device
#define SIM_DUMMY(inst)                                                                                                \
    DEVICE_DT_INST_DEFINE(inst, NULL, NULL, NULL, NULL, POST_KERNEL, CONFIG_KERNEL_INIT_PRIORITY_DEVICE, NULL);
DT_INST_FOREACH_STATUS_OKAY(SIM_DUMMY)
