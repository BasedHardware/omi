/*
 * sd_card.c â€” LittleFS over disk_access (SD NAND via SPI SD protocol)
 *
 * Architecture:
 *   SD NAND chip â†’ SD SPI stack (disk_access) â†’ LittleFS block callbacks
 *
 * Why LittleFS instead of FATFS:
 *   - Copy-on-write metadata: filesystem is always consistent after power loss
 *   - No "dirty bit" that causes FATFS to refuse writes after ungraceful shutdown
 *   - Journaling: data integrity without complex recovery code
 *   - SD card handles erase internally â†’ erase callback is a no-op
 *   - SD card has internal wear leveling â†’ block_cycles = -1
 */
#include "lib/core/sd_card.h"
#include "rtc.h"
#include <lfs.h>
#include <string.h>
#include <strings.h>
#include <stdlib.h>
#include <ctype.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device.h>
#include <zephyr/storage/disk_access.h>

LOG_MODULE_REGISTER(sd_card, CONFIG_LOG_DEFAULT_LEVEL);

#define DISK_DRIVE_NAME     CONFIG_SDMMC_VOLUME_NAME
#define SD_REQ_QUEUE_MSGS   100
#define SD_FSYNC_INTERVAL_MS          (5 * 60 * 1000)
#define WRITE_BATCH_COUNT   100
#define ERROR_THRESHOLD     5

/* LittleFS paths are relative to FS root (no mount-point prefix) */
#define FILE_DATA_DIR   "audio"
#define FILE_INFO_PATH  "info.txt"

/* ------------------------------------------------------------------ */
/* LittleFS state                                                      */
/* ------------------------------------------------------------------ */

/* Raw LFS instance */
static lfs_t lfs_fs;

/* Open file handles */
static lfs_file_t lfs_fil_data;
static lfs_file_t lfs_fil_info;

/* Static buffers for lfs_file_opencfg (avoids heap allocation)
 * Size must match cache_size (LFS_CACHE_SIZE = 4096). */
static uint8_t lfs_fdata_buf[4096];
static uint8_t lfs_finfo_buf[4096];
static struct lfs_file_config lfs_fdata_cfg = { .buffer = lfs_fdata_buf };
static struct lfs_file_config lfs_finfo_cfg = { .buffer = lfs_finfo_buf };

/* LFS I/O buffers — sized to cache_size (4096) for multi-sector I/O */
static uint8_t lfs_read_buf[4096];
static uint8_t lfs_prog_buf[4096];
static uint8_t lfs_lookahead_buf[128];  /* 128 bytes = 1024 blocks * 4096 = 4 MB lookahead */

/* Shared temp sector buffer â€” only used from worker thread, safe as static */
static uint8_t _lfs_io_tmp[512];

/* ------------------------------------------------------------------ */
/* Disk sector size (always 512 for SD) */
#define DISK_SECTOR_SIZE  512
/* LFS block size: groups 8 sectors into one LFS block.
 * With 512-byte blocks, a 512 MB SD has 1M blocks and LFS metadata overhead
 * is enormous (CTZ skip-lists, lookahead scans).  4096-byte blocks reduce
 * the block count to ~128K and cut metadata overhead by ~8x. */
#define LFS_BLOCK_SIZE    4096
#define LFS_CACHE_SIZE    LFS_BLOCK_SIZE  /* cache = 1 full block for multi-sector I/O */
#define SECTORS_PER_BLOCK (LFS_BLOCK_SIZE / DISK_SECTOR_SIZE)  /* 8 */
/* LittleFS disk_access callbacks                                      */
/* ------------------------------------------------------------------ */

/*
 * Map LFS (block, offset) to disk sector.
 *   LFS block N at byte offset K  →  disk sector  N * SECTORS_PER_BLOCK + K/512
 * With cache_size == 4096 (== block_size), LFS typically calls us with
 * size == 4096 and off == 0.  The fast path handles any aligned multi-sector
 * read in a single disk_access call (CMD18 multi-block read).
 */
static int lfs_disk_read_cb(const struct lfs_config *c, lfs_block_t block,
                             lfs_off_t off, void *buffer, lfs_size_t size)
{
    (void)c;
    uint32_t sector = (uint32_t)block * SECTORS_PER_BLOCK + off / DISK_SECTOR_SIZE;
    uint32_t sec_off = off % DISK_SECTOR_SIZE;

    /* Fast path: aligned multi-sector read (the common case with cache_size=4096) */
    if (sec_off == 0 && (size % DISK_SECTOR_SIZE) == 0) {
        uint32_t nsec = size / DISK_SECTOR_SIZE;
        return disk_access_read(DISK_DRIVE_NAME, buffer, sector, nsec) == 0
               ? LFS_ERR_OK : LFS_ERR_IO;
    }
    /* Generic path: partial / unaligned */
    uint8_t *dst = (uint8_t *)buffer;
    while (size > 0) {
        if (disk_access_read(DISK_DRIVE_NAME, _lfs_io_tmp, sector, 1) != 0)
            return LFS_ERR_IO;
        lfs_size_t chunk = DISK_SECTOR_SIZE - sec_off;
        if (chunk > size) chunk = size;
        memcpy(dst, _lfs_io_tmp + sec_off, chunk);
        dst     += chunk;
        size    -= chunk;
        sec_off  = 0;
        sector++;
    }
    return LFS_ERR_OK;
}

static int lfs_disk_prog_cb(const struct lfs_config *c, lfs_block_t block,
                             lfs_off_t off, const void *buffer, lfs_size_t size)
{
    (void)c;
    uint32_t sector = (uint32_t)block * SECTORS_PER_BLOCK + off / DISK_SECTOR_SIZE;
    uint32_t sec_off = off % DISK_SECTOR_SIZE;

    /* Fast path: aligned multi-sector write (CMD25 multi-block write) */
    if (sec_off == 0 && (size % DISK_SECTOR_SIZE) == 0) {
        uint32_t nsec = size / DISK_SECTOR_SIZE;
        return disk_access_write(DISK_DRIVE_NAME, buffer, sector, nsec) == 0
               ? LFS_ERR_OK : LFS_ERR_IO;
    }
    /* Generic path: read-modify-write per sector */
    const uint8_t *src = (const uint8_t *)buffer;
    while (size > 0) {
        if (disk_access_read(DISK_DRIVE_NAME, _lfs_io_tmp, sector, 1) != 0)
            return LFS_ERR_IO;
        lfs_size_t chunk = DISK_SECTOR_SIZE - sec_off;
        if (chunk > size) chunk = size;
        memcpy(_lfs_io_tmp + sec_off, src, chunk);
        if (disk_access_write(DISK_DRIVE_NAME, _lfs_io_tmp, sector, 1) != 0)
            return LFS_ERR_IO;
        src     += chunk;
        size    -= chunk;
        sec_off  = 0;
        sector++;
    }
    return LFS_ERR_OK;
}

static int lfs_disk_erase_cb(const struct lfs_config *c, lfs_block_t block)
{
    /* SD card erases blocks internally on write â€” this is a true no-op. */
    (void)c; (void)block;
    return LFS_ERR_OK;
}

static int lfs_disk_sync_cb(const struct lfs_config *c)
{
    (void)c;
    (void)disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_SYNC, NULL);
    return LFS_ERR_OK;
}

/* LFS config â€” block_count filled at runtime from DISK_IOCTL_GET_SECTOR_COUNT */
static struct lfs_config lfs_cfg = {
    .read  = lfs_disk_read_cb,
    .prog  = lfs_disk_prog_cb,
    .erase = lfs_disk_erase_cb,
    .sync  = lfs_disk_sync_cb,

    .read_size      = DISK_SECTOR_SIZE,
    .prog_size      = DISK_SECTOR_SIZE,
    .block_size     = LFS_BLOCK_SIZE,
    .block_count    = 0,    /* set at mount time */
    .cache_size     = LFS_CACHE_SIZE,   /* 4096: full-block cache → multi-sector I/O */
    .lookahead_size = 128,  /* must match lfs_lookahead_buf[] size (bytes, not bits) */

    .read_buffer      = lfs_read_buf,
    .prog_buffer      = lfs_prog_buf,
    .lookahead_buffer = lfs_lookahead_buf,

    /* SD card has internal wear leveling â†’ disable LFS wear leveling */
    .block_cycles = -1,
};

/* ------------------------------------------------------------------ */
/* Batch write buffer & general state                                  */
/* ------------------------------------------------------------------ */

static uint8_t write_batch_buffer[WRITE_BATCH_COUNT * MAX_WRITE_SIZE];
static size_t  write_batch_offset  = 0;
static int     write_batch_counter = 0;
static uint8_t writing_error_counter = 0;
static bool    sd_write_blocked    = false;
static int64_t last_write_blocked_log_ms = 0;

static bool     is_mounted  = false;
static bool     sd_enabled  = false;
static uint32_t current_file_size  = 0;
static size_t   bytes_since_sync   = 0;
static int64_t  last_file_sync_uptime_ms = 0;

/* Current writing file info */
static char    current_filename[MAX_FILENAME_LEN] = {0};
static char    current_file_path[64]              = {0};
static int64_t current_file_created_uptime_ms     = 0;
static bool    current_file_needs_rename          = false;

/* BLE connection tracking for file rotation */
static bool    ble_connected    = false;
static int64_t ble_connect_time_ms = 0;

/* Track if active file was deleted while BLE connected */
static bool current_file_deleted = false;

/* Offset info (oldest file + byte offset) */
static sd_offset_info_t current_offset_info = {0};

/* Hardware device references */
static const struct device *const sd_dev =
    DEVICE_DT_GET(DT_NODELABEL(sdhc0));
static const struct gpio_dt_spec sd_en =
    GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

K_MSGQ_DEFINE(sd_msgq, sizeof(sd_req_t), SD_REQ_QUEUE_MSGS, 4);

/* Priority queue for reads, flushes, and control operations.
 * The worker checks this BEFORE the regular write queue, so reads
 * never wait behind 100 pending audio writes. */
#define SD_PRIO_QUEUE_MSGS 10
K_MSGQ_DEFINE(sd_prio_msgq, sizeof(sd_req_t), SD_PRIO_QUEUE_MSGS, 4);

/* Persistent read file handle — kept open between read_audio_data calls
 * so we avoid the expensive LFS open/seek/close on every read.
 * With 512-byte blocks and a 1 MB+ file, an open+seek costs O(sqrt(N/512))
 * block reads (≈50 SPI transactions), making each read 100–300 ms.
 * Keeping the handle open reduces this to a simple sequential read (~5 ms). */
static lfs_file_t lfs_read_handle;
static uint8_t    lfs_read_handle_buf[4096];
static struct lfs_file_config lfs_read_handle_cfg = { .buffer = lfs_read_handle_buf };
static char  read_handle_filename[MAX_FILENAME_LEN] = {0};
static bool  read_handle_open   = false;
static lfs_soff_t read_handle_pos = 0;

/* Sync generation: incremented every time lfs_fil_data is synced.
 * The read handle records which generation it was opened at;
 * if it doesn't match, the handle is stale (file grew) and must reopen. */
static uint32_t data_sync_gen     = 0;
static uint32_t read_handle_gen   = 0;

static void close_read_handle(void)
{
    if (read_handle_open) {
        lfs_file_close(&lfs_fs, &lfs_read_handle);
        read_handle_open = false;
        read_handle_filename[0] = '\0';
        read_handle_pos = 0;
    }
}

void sd_worker_thread(void);

/* Forward declarations */
static int  create_audio_file_with_timestamp(void);
static int  flush_batch_buffer(void);
static void build_file_path(const char *filename, char *path, size_t path_size);

/* ------------------------------------------------------------------ */
/* Power management                                                    */
/* ------------------------------------------------------------------ */

static int sd_enable_power(bool enable)
{
    int ret;
    gpio_pin_configure_dt(&sd_en, GPIO_OUTPUT);
    const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi3));
    if (enable) {
        ret = gpio_pin_set_dt(&sd_en, 1);
        if (device_is_ready(spi_dev)) {
            pm_device_action_run(spi_dev, PM_DEVICE_ACTION_RESUME);
            pm_device_action_run(sd_dev, PM_DEVICE_ACTION_RESUME);
        }
        sd_enabled = true;
    } else {
        if (device_is_ready(spi_dev)) {
            pm_device_action_run(sd_dev, PM_DEVICE_ACTION_SUSPEND);
            pm_device_action_run(spi_dev, PM_DEVICE_ACTION_SUSPEND);
        }
        gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 11, GPIO_DISCONNECTED);
        ret = gpio_pin_set_dt(&sd_en, 0);
        sd_enabled = false;
    }
    return ret;
}

/* ------------------------------------------------------------------ */
/* LittleFS mount / unmount                                            */
/* ------------------------------------------------------------------ */

static void lfs_close_files(void)
{
    lfs_file_close(&lfs_fs, &lfs_fil_data);
    lfs_file_close(&lfs_fs, &lfs_fil_info);
    current_filename[0] = '\0';
    current_file_path[0] = '\0';
}

/*
 * Mount the filesystem.  LittleFS mounts existing FS or formats on first use.
 *
 * Key difference from FATFS: if there is any corruption LittleFS recovers
 * from its journal automatically â€” no mkfs needed, no power-loss dirty bit.
 */
static int sd_mount(void)
{
    if (is_mounted) {
        return 0;
    }

    /* Retry loop: SD NAND needs up to ~200 ms to stabilise after power-on.
     * CTRL_INIT returns EINVAL (-22) or EIO (-5) when the card isn't ready. */
    uint32_t sector_count = 0;
    uint32_t sector_size  = 0;
    int ret = -EIO;

    for (int attempt = 1; attempt <= 5; attempt++) {
        ret = sd_enable_power(true);
        if (ret < 0) {
            LOG_ERR("SD power on failed: %d", ret);
            return ret;
        }

        /* Progressive back-off: 50, 100, 150, 200, 250 ms */
        k_msleep(50 * attempt);

        ret = disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_INIT, NULL);
        if (ret == 0) {
            break;  /* init succeeded */
        }

        LOG_WRN("SD CTRL_INIT attempt %d/5 failed: %d", attempt, ret);
        (void)disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_DEINIT, NULL);
        sd_enable_power(false);
        k_msleep(50);
    }

    if (ret != 0) {
        LOG_ERR("Disk CTRL_INIT failed after retries: %d", ret);
        return ret;
    }

    disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_GET_SECTOR_COUNT, &sector_count);
    disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_GET_SECTOR_SIZE,  &sector_size);

    /* LittleFS only needs the disk to be 'initialised' from here on;
     * keep driver active (no CTRL_DEINIT) so callbacks work. */
    LOG_INF("SD: %u sectors x %u bytes = %u MB",
            sector_count, sector_size,
            (unsigned)((uint64_t)sector_count * sector_size >> 20));

    /* read/prog stay at sector granularity (512);
     * cache = full block (4096) for multi-sector I/O. */
    uint32_t ss = (sector_size > 0) ? sector_size : DISK_SECTOR_SIZE;
    lfs_cfg.read_size   = ss;
    lfs_cfg.prog_size   = ss;
    lfs_cfg.cache_size  = LFS_CACHE_SIZE;
    lfs_cfg.block_size  = LFS_BLOCK_SIZE;
    lfs_cfg.block_count = sector_count / (LFS_BLOCK_SIZE / ss);

    /* Try to mount existing filesystem */
    ret = lfs_mount(&lfs_fs, &lfs_cfg);
    if (ret != LFS_ERR_OK) {
        LOG_WRN("LFS mount failed (%d), formattingâ€¦", ret);
        ret = lfs_format(&lfs_fs, &lfs_cfg);
        if (ret != LFS_ERR_OK) {
            LOG_ERR("LFS format failed: %d", ret);
            sd_enable_power(false);
            return -EIO;
        }
        ret = lfs_mount(&lfs_fs, &lfs_cfg);
        if (ret != LFS_ERR_OK) {
            LOG_ERR("LFS mount after format failed: %d", ret);
            sd_enable_power(false);
            return -EIO;
        }
    }

    is_mounted = true;
    LOG_INF("LittleFS mounted OK");
    return 0;
}

static int sd_unmount(void)
{
    if (write_batch_offset > 0) {
        flush_batch_buffer();
    }
    close_read_handle();
    lfs_close_files();
    if (is_mounted) {
        lfs_unmount(&lfs_fs);
        is_mounted = false;
    }
    sd_enable_power(false);
    LOG_INF("LittleFS unmounted");
    return 0;
}

/* ------------------------------------------------------------------ */
/* Path helpers                                                        */
/* ------------------------------------------------------------------ */

static void build_file_path(const char *filename, char *path, size_t path_size)
{
    snprintf(path, path_size, "%s/%s", FILE_DATA_DIR, filename);
}

static bool filename_equals_ignore_case(const char *a, const char *b)
{
    if (!a || !b) return false;
    for (size_t i = 0; i < MAX_FILENAME_LEN; i++) {
        if (tolower((unsigned char)a[i]) != tolower((unsigned char)b[i])) return false;
        if (a[i] == '\0' || b[i] == '\0') break;
    }
    return true;
}

/* ------------------------------------------------------------------ */
/* Boot: list existing audio files                                     */
/* ------------------------------------------------------------------ */

static void print_audio_files_at_boot(void)
{
    lfs_dir_t dir;
    struct lfs_info info;
    uint32_t file_count = 0;
    uint64_t total_size = 0;

    if (lfs_dir_open(&lfs_fs, &dir, FILE_DATA_DIR) < 0) {
        LOG_INF("[SD_BOOT] No audio directory found");
        return;
    }

    LOG_INF("========== AUDIO FILES ON SD CARD ==========");
    while (lfs_dir_read(&lfs_fs, &dir, &info) > 0) {
        if (info.type != LFS_TYPE_REG) continue;
        char *dot = strrchr(info.name, '.');
        if (dot && strcasecmp(dot, ".txt") == 0) {
            LOG_INF("  [%u] %s - %u bytes",
                    file_count + 1, info.name, (unsigned)info.size);
            total_size += info.size;
            file_count++;
        }
    }
    lfs_dir_close(&lfs_fs, &dir);
    LOG_INF("[SD_BOOT] %u files, %u bytes total", file_count, (unsigned)total_size);
    LOG_INF("=============================================");
}

/* ------------------------------------------------------------------ */
/* File creation / continuation at boot                               */
/* ------------------------------------------------------------------ */

#define FILE_CONTINUE_THRESHOLD_SEC (30 * 60)

static int try_continue_latest_file(void)
{
    uint32_t current_time = get_utc_time();
    if (current_time == 0 || current_time < 1700000000U) {
        LOG_INF("[SD_BOOT] RTC not valid, will create new file");
        return -1;
    }

    lfs_dir_t dir;
    struct lfs_info info;
    if (lfs_dir_open(&lfs_fs, &dir, FILE_DATA_DIR) < 0) {
        return -1;
    }

    char    latest_filename[MAX_FILENAME_LEN] = {0};
    uint32_t latest_timestamp = 0;

    while (lfs_dir_read(&lfs_fs, &dir, &info) > 0) {
        if (info.type != LFS_TYPE_REG) continue;
        char *dot = strrchr(info.name, '.');
        if (dot && strcasecmp(dot, ".txt") == 0) {
            uint32_t ts = (uint32_t)strtoul(info.name, NULL, 16);
            if (ts > latest_timestamp) {
                latest_timestamp = ts;
                strncpy(latest_filename, info.name, sizeof(latest_filename) - 1);
            }
        }
    }
    lfs_dir_close(&lfs_fs, &dir);

    if (latest_filename[0] == '\0') return -1;

    int32_t diff = (int32_t)(current_time - latest_timestamp);
    LOG_INF("[SD_BOOT] Latest file: %s diff=%d s", latest_filename, diff);

    if (diff < 0 || diff > FILE_CONTINUE_THRESHOLD_SEC) return -1;

    strncpy(current_filename, latest_filename, sizeof(current_filename) - 1);
    build_file_path(current_filename, current_file_path, sizeof(current_file_path));

    int ret = lfs_file_opencfg(&lfs_fs, &lfs_fil_data, current_file_path,
                                LFS_O_RDWR | LFS_O_APPEND, &lfs_fdata_cfg);
    if (ret < 0) {
        LOG_ERR("[SD_BOOT] open existing file failed: %d", ret);
        current_filename[0] = '\0';
        return -1;
    }

    current_file_size             = (uint32_t)lfs_file_size(&lfs_fs, &lfs_fil_data);
    bytes_since_sync              = 0;
    write_batch_offset            = 0;
    write_batch_counter           = 0;
    last_file_sync_uptime_ms      = k_uptime_get();
    current_file_created_uptime_ms = k_uptime_get();
    current_file_needs_rename     = false;

    LOG_INF("[SD_BOOT] Continuing file: %s (%u bytes)", current_filename, current_file_size);
    return 0;
}

static int create_audio_file_with_timestamp(void)
{
    bool     rtc_valid = rtc_is_valid();
    uint32_t timestamp = 0;

    if (rtc_valid) {
        timestamp = get_utc_time();
        if (timestamp == 0 || timestamp < 1700000000U) rtc_valid = false;
    }

    /* Close current file if open */
    if (current_filename[0] != '\0') {
        if (write_batch_offset > 0) flush_batch_buffer();
        lfs_file_close(&lfs_fs, &lfs_fil_data);
        current_filename[0] = '\0';
    }

    /* Ensure audio directory exists */
    struct lfs_info dir_info;
    if (lfs_stat(&lfs_fs, FILE_DATA_DIR, &dir_info) < 0) {
        int mk = lfs_mkdir(&lfs_fs, FILE_DATA_DIR);
        if (mk < 0 && mk != LFS_ERR_EXIST) {
            LOG_ERR("mkdir %s failed: %d", FILE_DATA_DIR, mk);
            return mk;
        }
    }

    if (rtc_valid) {
        snprintf(current_filename, sizeof(current_filename), "%08X.txt", timestamp);
        current_file_needs_rename = false;
    } else {
        uint32_t uptime_s = (uint32_t)(k_uptime_get() / 1000);
        snprintf(current_filename, sizeof(current_filename), "TMP_%04X.txt", uptime_s & 0xFFFFU);
        current_file_needs_rename = true;
        LOG_WRN("RTC not synced, temp file: %s", current_filename);
    }

    build_file_path(current_filename, current_file_path, sizeof(current_file_path));
    LOG_INF("Creating audio file: %s", current_file_path);

    int ret = lfs_file_opencfg(&lfs_fs, &lfs_fil_data, current_file_path,
                                LFS_O_CREAT | LFS_O_RDWR | LFS_O_APPEND, &lfs_fdata_cfg);
    if (ret < 0) {
        LOG_ERR("Failed to create %s: %d", current_file_path, ret);
        current_filename[0] = '\0';
        current_file_path[0] = '\0';
        return ret;
    }

    current_file_size             = 0;
    bytes_since_sync              = 0;
    write_batch_offset            = 0;
    write_batch_counter           = 0;
    writing_error_counter         = 0;
    sd_write_blocked              = false;
    last_file_sync_uptime_ms      = k_uptime_get();
    current_file_created_uptime_ms = k_uptime_get();

    LOG_INF("Audio file created: %s", current_filename);
    return 0;
}

/* ------------------------------------------------------------------ */
/* Batch buffer flush                                                  */
/* ------------------------------------------------------------------ */

static int flush_batch_buffer(void)
{
    if (write_batch_offset == 0) return 0;

    if (sd_write_blocked) {
        write_batch_offset  = 0;
        write_batch_counter = 0;
        return -EIO;
    }

    lfs_ssize_t bw = lfs_file_write(&lfs_fs, &lfs_fil_data,
                                     write_batch_buffer, write_batch_offset);
    if (bw < 0 || (size_t)bw != write_batch_offset) {
        writing_error_counter++;
        LOG_ERR("batch write error bw=%d wanted=%u", (int)bw, (unsigned)write_batch_offset);

        if (writing_error_counter > ERROR_THRESHOLD) {
            sd_write_blocked = true;
            LOG_ERR("Too many write errors, blocking write queue");
        }
        write_batch_offset  = 0;
        write_batch_counter = 0;
        return -EIO;
    }

    bytes_since_sync    += (size_t)bw;
    current_file_size   += (uint32_t)bw;
    write_batch_offset   = 0;
    write_batch_counter  = 0;
    writing_error_counter = 0;
    return 0;
}

/* ------------------------------------------------------------------ */
/* File rotation helper                                                */
/* ------------------------------------------------------------------ */

static bool should_rotate_file(void)
{
    if (current_file_created_uptime_ms == 0) return false;
    return (k_uptime_get() - current_file_created_uptime_ms) >= FILE_ROTATION_INTERVAL_MS;
}

/* ------------------------------------------------------------------ */
/* Filename sort (hex timestamp, oldest first)                        */
/* ------------------------------------------------------------------ */

static int compare_filenames(const void *a, const void *b)
{
    uint32_t ta = (uint32_t)strtoul((const char *)a, NULL, 16);
    uint32_t tb = (uint32_t)strtoul((const char *)b, NULL, 16);
    return (ta < tb) ? -1 : (ta > tb) ? 1 : 0;
}

/* ------------------------------------------------------------------ */
/* Filename rename after time-sync                                     */
/* ------------------------------------------------------------------ */

void sd_update_filename_after_timesync(uint32_t synced_utc_time)
{
    if (!current_file_needs_rename || current_filename[0] == '\0' || !is_mounted) return;

    int64_t  now_ms    = k_uptime_get();
    uint32_t elapsed   = (uint32_t)(now_ms - current_file_created_uptime_ms);
    uint32_t correct_ts = synced_utc_time - (elapsed / 1000U);

    char new_filename[MAX_FILENAME_LEN];
    snprintf(new_filename, sizeof(new_filename), "%08X.txt", correct_ts);
    LOG_INF("Rename: %s -> %s (elapsed=%u ms)", current_filename, new_filename, elapsed);

    if (write_batch_offset > 0) flush_batch_buffer();
    lfs_file_sync(&lfs_fs, &lfs_fil_data);
    data_sync_gen++;
    bytes_since_sync = 0;
    last_file_sync_uptime_ms = k_uptime_get();
    lfs_file_close(&lfs_fs, &lfs_fil_data);

    char new_path[64];
    build_file_path(new_filename, new_path, sizeof(new_path));
    int ret = lfs_rename(&lfs_fs, current_file_path, new_path);
    if (ret < 0) {
        LOG_ERR("Rename failed: %d", ret);
        /* Re-open old file */
        lfs_file_opencfg(&lfs_fs, &lfs_fil_data, current_file_path,
                          LFS_O_RDWR | LFS_O_APPEND, &lfs_fdata_cfg);
        return;
    }

    strncpy(current_filename,  new_filename, sizeof(current_filename) - 1);
    strncpy(current_file_path, new_path,     sizeof(current_file_path) - 1);
    current_file_needs_rename = false;

    lfs_file_opencfg(&lfs_fs, &lfs_fil_data, current_file_path,
                      LFS_O_RDWR | LFS_O_APPEND, &lfs_fdata_cfg);
    LOG_INF("File renamed OK: %s", current_filename);
}

/* ------------------------------------------------------------------ */
/* Worker thread & task definitions                                    */
/* ------------------------------------------------------------------ */

#define SD_WORKER_STACK_SIZE 16384
#define SD_WORKER_PRIORITY   7
K_THREAD_STACK_DEFINE(sd_worker_stack, SD_WORKER_STACK_SIZE);
static struct k_thread sd_worker_thread_data;
static k_tid_t sd_worker_tid = NULL;

/* ------------------------------------------------------------------ */
/* Internal helpers: file list, file stats                            */
/* ------------------------------------------------------------------ */

static int get_audio_file_list_internal(char filenames[][MAX_FILENAME_LEN],
                                        uint32_t *sizes, int max_files, int *count)
{
    if (!filenames || !count || max_files <= 0) return -EINVAL;
    if (!is_mounted) return -ENODEV;

    lfs_dir_t dir;
    struct lfs_info info;
    int file_count = 0;
    static uint32_t tmp_sizes[MAX_AUDIO_FILES];

    if (lfs_dir_open(&lfs_fs, &dir, FILE_DATA_DIR) < 0) return -ENOENT;

    while (file_count < max_files) {
        int rc = lfs_dir_read(&lfs_fs, &dir, &info);
        if (rc <= 0) break;
        if (info.type != LFS_TYPE_REG) continue;
        char *dot = strrchr(info.name, '.');
        if (dot && strcasecmp(dot, ".txt") == 0) {
            strncpy(filenames[file_count], info.name, MAX_FILENAME_LEN - 1);
            filenames[file_count][MAX_FILENAME_LEN - 1] = '\0';
            tmp_sizes[file_count] = (uint32_t)info.size;
            file_count++;
        }
    }
    lfs_dir_close(&lfs_fs, &dir);

    /* Sort filenames and keep sizes in sync (insertion sort) */
    if (file_count > 1) {
        for (int i = 1; i < file_count; i++) {
            char tmp_name[MAX_FILENAME_LEN];
            uint32_t tmp_sz = tmp_sizes[i];
            strncpy(tmp_name, filenames[i], MAX_FILENAME_LEN);
            int j = i - 1;
            while (j >= 0 && strcmp(filenames[j], tmp_name) > 0) {
                strncpy(filenames[j + 1], filenames[j], MAX_FILENAME_LEN);
                tmp_sizes[j + 1] = tmp_sizes[j];
                j--;
            }
            strncpy(filenames[j + 1], tmp_name, MAX_FILENAME_LEN);
            tmp_sizes[j + 1] = tmp_sz;
        }
    }

    if (sizes) {
        /* Fix up size for the currently-open file: directory entry
         * may be stale, use tracked current_file_size instead */
        for (int i = 0; i < file_count; i++) {
            if (current_filename[0] != '\0' &&
                strcmp(filenames[i], current_filename) == 0) {
                tmp_sizes[i] = current_file_size;
                break;
            }
        }
        memcpy(sizes, tmp_sizes, file_count * sizeof(uint32_t));
    }
    *count = file_count;
    return 0;
}

/* ------------------------------------------------------------------ */
/* SD worker thread                                                    */
/* ------------------------------------------------------------------ */

void sd_worker_thread(void)
{
    sd_req_t req;
    int res;

    /* ---- Mount ---- */
    res = sd_mount();
    if (res != 0) {
        LOG_ERR("[SD_WORK] mount failed: %d", res);
        sd_write_blocked = true;
        return;
    }

    /* ---- Ensure audio directory exists ---- */
    struct lfs_info dir_info;
    if (lfs_stat(&lfs_fs, FILE_DATA_DIR, &dir_info) < 0) {
        int mk = lfs_mkdir(&lfs_fs, FILE_DATA_DIR);
        if (mk < 0 && mk != LFS_ERR_EXIST) {
            LOG_ERR("[SD_WORK] mkdir audio failed: %d â€” write path blocked", mk);
            sd_write_blocked = true;
        }
    }

    /* ---- Print existing files at boot ---- */
    print_audio_files_at_boot();

    /* ---- Open / create info file ---- */
    {
        struct lfs_info info_lstat;
        bool info_exists   = (lfs_stat(&lfs_fs, FILE_INFO_PATH, &info_lstat) == 0);
        bool need_init_off = !info_exists || (info_lstat.size < sizeof(sd_offset_info_t));

        res = lfs_file_opencfg(&lfs_fs, &lfs_fil_info, FILE_INFO_PATH,
                                LFS_O_CREAT | LFS_O_RDWR, &lfs_finfo_cfg);
        if (res < 0) {
            LOG_ERR("[SD_WORK] open info failed: %d", res);
            sd_write_blocked = true;
        } else if (need_init_off) {
            memset(&current_offset_info, 0, sizeof(current_offset_info));
            lfs_ssize_t bw = lfs_file_write(&lfs_fs, &lfs_fil_info,
                                             &current_offset_info,
                                             sizeof(current_offset_info));
            if (bw != (lfs_ssize_t)sizeof(current_offset_info)) {
                LOG_ERR("[SD_WORK] init info write failed: %d", (int)bw);
            } else {
                lfs_file_sync(&lfs_fs, &lfs_fil_info);
            }
        } else {
            lfs_file_seek(&lfs_fs, &lfs_fil_info, 0, LFS_SEEK_SET);
            lfs_ssize_t rb = lfs_file_read(&lfs_fs, &lfs_fil_info,
                                            &current_offset_info,
                                            sizeof(current_offset_info));
            if (rb != (lfs_ssize_t)sizeof(current_offset_info)) {
                LOG_ERR("[SD_WORK] read offset info failed: %d", (int)rb);
                memset(&current_offset_info, 0, sizeof(current_offset_info));
            } else {
                LOG_INF("[SD_WORK] Loaded offset: file=%s off=%u",
                        current_offset_info.oldest_filename,
                        current_offset_info.offset_in_file);
            }
        }
    }

    /* ---- Open initial audio file ---- */
    res = try_continue_latest_file();
    if (res < 0) {
        res = create_audio_file_with_timestamp();
        if (res < 0) {
            LOG_ERR("[SD_WORK] initial file create failed: %d â€” write blocked", res);
            sd_write_blocked = true;
        }
    }

    /* ---- Main loop ---- */
    while (1) {
        /* Priority queue first: reads, flush, file-list, delete, etc.
         * These never wait behind pending audio writes. */
        if (k_msgq_get(&sd_prio_msgq, &req, K_NO_WAIT) == 0) {
            /* Flush any buffered writes before handling control op */
            if (write_batch_offset > 0) flush_batch_buffer();
            goto handle_req;
        }

        /* Regular write queue timeout: short when BLE connected (keep read/sync responsive),
         * long when offline (save power). */
        k_timeout_t write_wait = ble_connected ? K_MSEC(50) : K_MSEC(500);
        if (k_msgq_get(&sd_msgq, &req, write_wait) != 0) continue;

handle_req:
        switch (req.type) {

        /* ---- Write data ---- */
        case REQ_WRITE_DATA:
            if (sd_write_blocked) break;
            if (current_file_deleted && ble_connected) break;

            if (current_filename[0] == '\0') {
                res = create_audio_file_with_timestamp();
                if (res < 0) { sd_write_blocked = true; break; }
            }

            if (should_rotate_file()) {
                LOG_INF("[SD_WORK] Rotating file after 30 min");
                flush_batch_buffer();
                create_audio_file_with_timestamp();
            }

            memcpy(write_batch_buffer + write_batch_offset,
                   req.u.write.buf, req.u.write.len);
            write_batch_offset  += req.u.write.len;
            write_batch_counter++;

            if (write_batch_counter >= WRITE_BATCH_COUNT) {
                flush_batch_buffer();
            }

            bool sync_due_to_interval =
                (bytes_since_sync > 0) &&
                ((k_uptime_get() - last_file_sync_uptime_ms) >= SD_FSYNC_INTERVAL_MS);

            if (sync_due_to_interval) {
                lfs_file_sync(&lfs_fs, &lfs_fil_data);
                data_sync_gen++;
                bytes_since_sync = 0;
                last_file_sync_uptime_ms = k_uptime_get();
            }
            break;

        /* ---- Read audio data (uses persistent file handle) ---- */
        case REQ_READ_DATA: {
            char read_path[64];
            build_file_path(req.u.read.filename, read_path, sizeof(read_path));

            bool is_active_file = (current_filename[0] != '\0' &&
                                   strcmp(req.u.read.filename, current_filename) == 0);

            /* Close handle if different file requested */
            if (read_handle_open &&
                strcmp(read_handle_filename, req.u.read.filename) != 0) {
                close_read_handle();
            }

            /* Reopen if handle is stale (file was synced since handle opened) */
            if (read_handle_open && read_handle_gen != data_sync_gen) {
                close_read_handle();
            }

            /* Open file if not already open */
            if (!read_handle_open) {
                res = lfs_file_opencfg(&lfs_fs, &lfs_read_handle, read_path,
                                        LFS_O_RDONLY, &lfs_read_handle_cfg);
                if (res < 0) {
                    LOG_ERR("[SD_WORK] open read failed: %s err=%d", read_path, res);
                    if (req.u.read.resp) {
                        req.u.read.resp->res = res;
                        req.u.read.resp->read_bytes = 0;
                        k_sem_give(&req.u.read.resp->sem);
                    }
                    break;
                }
                strncpy(read_handle_filename, req.u.read.filename,
                        MAX_FILENAME_LEN - 1);
                read_handle_open = true;
                read_handle_pos  = 0;
                read_handle_gen  = data_sync_gen;
            }

            /* Only seek if position doesn't match (sequential reads skip seek) */
            if (read_handle_pos != (lfs_soff_t)req.u.read.offset) {
                lfs_file_seek(&lfs_fs, &lfs_read_handle,
                              (lfs_soff_t)req.u.read.offset, LFS_SEEK_SET);
                read_handle_pos = (lfs_soff_t)req.u.read.offset;
            }

            lfs_ssize_t br = lfs_file_read(&lfs_fs, &lfs_read_handle,
                                            req.u.read.out_buf, req.u.read.length);

            /* Lazy sync: if we got 0 bytes (EOF) on the active file and
             * there is uncommitted data, flush+sync now and retry once.
             * This avoids the expensive lfs_file_sync on EVERY read
             * (was ~50-100 ms each) — we only pay the cost when we
             * actually hit the stale-EOF boundary. */
            if (br == 0 && is_active_file &&
                (write_batch_offset > 0 || bytes_since_sync > 0)) {
                if (write_batch_offset > 0) {
                    flush_batch_buffer();
                }
                if (bytes_since_sync > 0) {
                    lfs_file_sync(&lfs_fs, &lfs_fil_data);
                    data_sync_gen++;
                    bytes_since_sync = 0;
                    last_file_sync_uptime_ms = k_uptime_get();
                }
                /* Reopen read handle to pick up new file size */
                close_read_handle();
                res = lfs_file_opencfg(&lfs_fs, &lfs_read_handle, read_path,
                                        LFS_O_RDONLY, &lfs_read_handle_cfg);
                if (res < 0) {
                    if (req.u.read.resp) {
                        req.u.read.resp->res = res;
                        req.u.read.resp->read_bytes = 0;
                        k_sem_give(&req.u.read.resp->sem);
                    }
                    break;
                }
                strncpy(read_handle_filename, req.u.read.filename,
                        MAX_FILENAME_LEN - 1);
                read_handle_open = true;
                read_handle_pos  = 0;
                read_handle_gen  = data_sync_gen;

                lfs_file_seek(&lfs_fs, &lfs_read_handle,
                              (lfs_soff_t)req.u.read.offset, LFS_SEEK_SET);
                read_handle_pos = (lfs_soff_t)req.u.read.offset;

                br = lfs_file_read(&lfs_fs, &lfs_read_handle,
                                   req.u.read.out_buf, req.u.read.length);
            }

            if (br > 0) {
                read_handle_pos += br;
            }

            if (req.u.read.resp) {
                req.u.read.resp->res = (br < 0) ? (int)br : 0;
                req.u.read.resp->read_bytes = (br < 0) ? 0 : (int)br;
                k_sem_give(&req.u.read.resp->sem);
            }
            break;
        }

        /* ---- Save offset ---- */
        case REQ_SAVE_OFFSET:
            if (sd_write_blocked) break;
            lfs_file_seek(&lfs_fs, &lfs_fil_info, 0, LFS_SEEK_SET);
            {
                lfs_ssize_t bw = lfs_file_write(&lfs_fs, &lfs_fil_info,
                                                 &req.u.info.offset_info,
                                                 sizeof(sd_offset_info_t));
                if (bw == (lfs_ssize_t)sizeof(sd_offset_info_t)) {
                    lfs_file_sync(&lfs_fs, &lfs_fil_info);
                    memcpy(&current_offset_info, &req.u.info.offset_info,
                           sizeof(sd_offset_info_t));
                } else {
                    LOG_ERR("[SD_WORK] save offset write err %d", (int)bw);
                }
            }
            break;

        /* ---- Clear audio directory ---- */
        case REQ_CLEAR_AUDIO_DIR: {
            flush_batch_buffer();
            close_read_handle();
            lfs_file_close(&lfs_fs, &lfs_fil_data);
            current_filename[0] = '\0';

            lfs_dir_t dir;
            struct lfs_info info;
            char fpath[64];

            if (lfs_dir_open(&lfs_fs, &dir, FILE_DATA_DIR) == 0) {
                while (lfs_dir_read(&lfs_fs, &dir, &info) > 0) {
                    if (info.type != LFS_TYPE_REG) continue;
                    build_file_path(info.name, fpath, sizeof(fpath));
                    int rm = lfs_remove(&lfs_fs, fpath);
                    if (rm < 0) LOG_ERR("[SD_WORK] rm %s: %d", fpath, rm);
                }
                lfs_dir_close(&lfs_fs, &dir);
            }

            /* Reset offset info */
            memset(&current_offset_info, 0, sizeof(current_offset_info));
            lfs_file_seek(&lfs_fs, &lfs_fil_info, 0, LFS_SEEK_SET);
            lfs_file_write(&lfs_fs, &lfs_fil_info,
                           &current_offset_info, sizeof(current_offset_info));
            lfs_file_sync(&lfs_fs, &lfs_fil_info);

            res = create_audio_file_with_timestamp();

            if (req.u.clear_dir.resp) {
                req.u.clear_dir.resp->res = res;
                k_sem_give(&req.u.clear_dir.resp->sem);
            }
            break;
        }

        /* ---- Create new file ---- */
        case REQ_CREATE_NEW_FILE:
            flush_batch_buffer();
            res = create_audio_file_with_timestamp();
            if (req.u.create_file.resp) {
                req.u.create_file.resp->res = res;
                k_sem_give(&req.u.create_file.resp->sem);
            }
            break;

        /* ---- Get file stats ---- */
        case REQ_GET_FILE_STATS: {
            lfs_dir_t dir;
            struct lfs_info info;
            char fpath[64];
            uint32_t file_count = 0;
            uint64_t total_size = 0;

            res = lfs_dir_open(&lfs_fs, &dir, FILE_DATA_DIR);
            if (res < 0) {
                if (req.u.file_stats.resp) {
                    req.u.file_stats.resp->res = res;
                    req.u.file_stats.resp->file_count = 0;
                    req.u.file_stats.resp->total_size = 0;
                    k_sem_give(&req.u.file_stats.resp->sem);
                }
                break;
            }
            while (lfs_dir_read(&lfs_fs, &dir, &info) > 0) {
                if (info.type != LFS_TYPE_REG) continue;
                char *dot = strrchr(info.name, '.');
                if (dot && strcasecmp(dot, ".txt") == 0) {
                    file_count++;
                    total_size += info.size;
                    (void)fpath; /* used to silence unused warning â€” path not needed */
                }
            }
            lfs_dir_close(&lfs_fs, &dir);

            if (req.u.file_stats.resp) {
                req.u.file_stats.resp->res = 0;
                req.u.file_stats.resp->file_count = file_count;
                req.u.file_stats.resp->total_size = total_size;
                k_sem_give(&req.u.file_stats.resp->sem);
            }
            break;
        }

        /* ---- Get file list ---- */
        case REQ_GET_FILE_LIST: {
            int list_count = 0;
            res = get_audio_file_list_internal(
                req.u.file_list.filenames,
                req.u.file_list.sizes,
                req.u.file_list.max_files,
                &list_count);
            if (req.u.file_list.resp) {
                req.u.file_list.resp->res   = res;
                req.u.file_list.resp->count = (res == 0) ? list_count : 0;
                k_sem_give(&req.u.file_list.resp->sem);
            }
            break;
        }

        /* ---- Flush current file ---- */
        case REQ_FLUSH_FILE: {
            int flush_res = 0;
            if (!current_file_deleted && current_filename[0] != '\0') {
                flush_res = flush_batch_buffer();
                if (flush_res == 0) {
                    int sr = lfs_file_sync(&lfs_fs, &lfs_fil_data);
                    if (sr < 0) {
                        LOG_ERR("[SD_WORK] lfs_file_sync failed: %d", sr);
                        flush_res = sr;
                    } else {
                        data_sync_gen++;
                        bytes_since_sync = 0;
                        last_file_sync_uptime_ms = k_uptime_get();
                        LOG_INF("[SD_WORK] Flushed %s (%u bytes)",
                                current_filename, current_file_size);
                    }
                }
            }
            if (req.u.create_file.resp) {
                req.u.create_file.resp->res = flush_res;
                k_sem_give(&req.u.create_file.resp->sem);
            }
            break;
        }

        /* ---- Delete file ---- */
        case REQ_DELETE_FILE: {
            char del_path[64];
            build_file_path(req.u.delete_file.filename, del_path, sizeof(del_path));

            /* Close read handle if we're about to delete the file being read */
            if (read_handle_open &&
                filename_equals_ignore_case(read_handle_filename,
                                            req.u.delete_file.filename)) {
                close_read_handle();
            }

            if (current_filename[0] != '\0' &&
                filename_equals_ignore_case(current_filename,
                                            req.u.delete_file.filename)) {
                LOG_INF("[SD_WORK] Deleting active recording file");
                flush_batch_buffer();
                lfs_file_close(&lfs_fs, &lfs_fil_data);
                current_filename[0] = '\0';
                current_file_path[0] = '\0';
                current_file_size    = 0;
                bytes_since_sync     = 0;
                last_file_sync_uptime_ms = 0;
                write_batch_offset   = 0;
                write_batch_counter  = 0;
                current_file_deleted = true;
            }

            int rm = lfs_remove(&lfs_fs, del_path);
            if (rm < 0 && rm != LFS_ERR_NOENT) {
                LOG_ERR("[SD_WORK] remove %s failed: %d", del_path, rm);
            }
            if (req.u.delete_file.resp) {
                req.u.delete_file.resp->res = rm;
                k_sem_give(&req.u.delete_file.resp->sem);
            }
            break;
        }

        /* ---- Time synced ---- */
        case REQ_TIME_SYNCED:
            if (current_file_needs_rename && current_filename[0] != '\0') {
                sd_update_filename_after_timesync(req.u.time_synced.utc_time);
            } else if (current_filename[0] == '\0') {
                res = create_audio_file_with_timestamp();
                if (res < 0) LOG_ERR("[SD_WORK] create after time sync failed: %d", res);
            }
            break;

        default:
            LOG_ERR("[SD_WORK] unknown request type %d", req.type);
        }
    }
}

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */

int app_sd_init(void)
{
    if (!sd_worker_tid) {
        sd_worker_tid = k_thread_create(
            &sd_worker_thread_data, sd_worker_stack, SD_WORKER_STACK_SIZE,
            (k_thread_entry_t)sd_worker_thread, NULL, NULL, NULL,
            SD_WORKER_PRIORITY, 0, K_NO_WAIT);
        k_thread_name_set(sd_worker_tid, "sd_worker");
    }
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

uint32_t get_file_size(void)
{
    return current_file_size;
}

int get_current_filename(char *buf, size_t buf_size)
{
    if (!buf || buf_size < MAX_FILENAME_LEN) return -EINVAL;
    strncpy(buf, current_filename, buf_size - 1);
    buf[buf_size - 1] = '\0';
    return 0;
}

void sd_notify_time_synced(uint32_t utc_time)
{
    sd_req_t req = {0};
    req.type = REQ_TIME_SYNCED;
    req.u.time_synced.utc_time = utc_time;
    /* Use priority queue so this doesn't fail when write queue is full */
    int ret = k_msgq_put(&sd_prio_msgq, &req, K_NO_WAIT);
    if (ret) LOG_ERR("Failed to queue time_synced: %d", ret);
}

void sd_notify_ble_state(bool connected)
{
    if (connected && !ble_connected) {
        ble_connect_time_ms = k_uptime_get();
        LOG_INF("BLE connected");
        /* Fire-and-forget flush via prio queue.
         * Do NOT block here — this runs on the BLE callback thread;
         * a blocking call would freeze the BLE stack and cause
         * ATT Timeout → disconnect.  The storage auto-sync will
         * flush before reading anyway. */
        sd_req_t req = {0};
        req.type = REQ_FLUSH_FILE;
        req.u.create_file.resp = NULL;  /* no response needed */
        int ret = k_msgq_put(&sd_prio_msgq, &req, K_NO_WAIT);
        if (ret) LOG_WRN("Flush on BLE connect: queue full (%d)", ret);
    } else if (!connected && ble_connected) {
        LOG_INF("BLE disconnected");
        if (current_file_deleted) {
            int cr = create_new_audio_file();
            if (cr < 0) LOG_ERR("create file on BLE disconnect failed: %d", cr);
            else current_file_deleted = false;
        }
    }
    ble_connected = connected;
}

uint32_t write_to_file(uint8_t *data, uint32_t length)
{
    static int64_t last_write_err_log_ms;
    if (sd_write_blocked) {
        int64_t now = k_uptime_get();
        if (now - last_write_blocked_log_ms > 1000) {
            LOG_ERR("write_to_file blocked");
            last_write_blocked_log_ms = now;
        }
        return 0;
    }
    sd_req_t req = {0};
    req.type = REQ_WRITE_DATA;
    memcpy(req.u.write.buf, data, length);
    req.u.write.len = length;
    /* Non-blocking put: audio writes are fire-and-forget.
     * If the queue is full (worker busy with slow I/O), we drop
     * the write rather than blocking the caller for 100ms. */
    int ret = k_msgq_put(&sd_msgq, &req, K_NO_WAIT);
    if (ret) {
        int64_t now = k_uptime_get();
        if (now - last_write_err_log_ms > 2000) {
            LOG_WRN("Write queue full, dropping audio data (%d)", ret);
            last_write_err_log_ms = now;
        }
        return 0;
    }
    return length;
}

int read_audio_data(const char *filename, uint8_t *buf, int amount, int offset)
{
    /* Static resp so worker never writes to freed stack memory on timeout */
    static struct read_resp resp;
    static volatile bool read_in_flight;

    if (read_in_flight) {
        /* Check if late worker response arrived */
        if (k_sem_take(&resp.sem, K_NO_WAIT) == 0) {
            read_in_flight = false; /* Worker caught up */
        } else {
            LOG_WRN("read_audio_data: previous request still in-flight");
            return -EBUSY;
        }
    }
    read_in_flight = true;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_READ_DATA;
    strncpy(req.u.read.filename, filename, MAX_FILENAME_LEN - 1);
    req.u.read.out_buf = buf;
    req.u.read.length  = amount;
    req.u.read.offset  = offset;
    req.u.read.resp    = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret) {
        LOG_ERR("Failed to queue read: %d", ret);
        read_in_flight = false;
        return ret;
    }

    if (k_sem_take(&resp.sem, K_MSEC(15000)) != 0) {
        LOG_ERR("Timeout waiting for read");
        /* Worker may still write to static resp later — that's safe.
         * Next call will check if worker caught up via sem. */
        return -ETIMEDOUT;
    }
    read_in_flight = false;
    if (resp.res) { LOG_ERR("read_audio_data failed: %d", resp.res); return -1; }
    return resp.read_bytes;
}

int sd_flush_current_file(void)
{
    static struct read_resp resp;
    static volatile bool flush_in_flight;

    if (flush_in_flight) {
        if (k_sem_take(&resp.sem, K_NO_WAIT) == 0) {
            flush_in_flight = false;
        } else {
            LOG_WRN("sd_flush: previous flush still in-flight");
            return -EBUSY;
        }
    }
    flush_in_flight = true;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_FLUSH_FILE;
    req.u.create_file.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret) {
        LOG_ERR("Failed to queue flush: %d", ret);
        flush_in_flight = false;
        return ret;
    }

    if (k_sem_take(&resp.sem, K_MSEC(30000)) != 0) {
        LOG_ERR("Timeout waiting for flush");
        return -ETIMEDOUT;
    }
    flush_in_flight = false;
    return resp.res;
}

int delete_audio_file(const char *filename)
{
    if (!filename) return -EINVAL;

    static struct read_resp resp;
    static volatile bool delete_in_flight;

    if (delete_in_flight) {
        if (k_sem_take(&resp.sem, K_NO_WAIT) == 0) {
            delete_in_flight = false;
        } else {
            LOG_WRN("delete_audio_file: previous delete still in-flight");
            return -EBUSY;
        }
    }
    delete_in_flight = true;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_DELETE_FILE;
    strncpy(req.u.delete_file.filename, filename, MAX_FILENAME_LEN - 1);
    req.u.delete_file.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret) {
        LOG_ERR("Failed to queue delete: %d", ret);
        delete_in_flight = false;
        return ret;
    }

    if (k_sem_take(&resp.sem, K_MSEC(30000)) != 0) {
        LOG_ERR("Timeout waiting for delete");
        return -ETIMEDOUT;
    }
    delete_in_flight = false;
    if (resp.res < 0 && resp.res != -ENOENT) {
        LOG_ERR("delete_audio_file %s failed: %d", filename, resp.res);
        return resp.res;
    }
    return 0;
}

int clear_audio_directory(void)
{
    static struct read_resp resp;
    static volatile bool clear_in_flight;

    if (clear_in_flight) {
        if (k_sem_take(&resp.sem, K_NO_WAIT) == 0) {
            clear_in_flight = false;
        } else {
            LOG_WRN("clear_audio_directory: previous clear still in-flight");
            return -EBUSY;
        }
    }
    clear_in_flight = true;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_CLEAR_AUDIO_DIR;
    req.u.clear_dir.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret) {
        LOG_ERR("Failed to queue clear_dir: %d", ret);
        clear_in_flight = false;
        return -1;
    }

    if (k_sem_take(&resp.sem, K_MSEC(60000)) != 0) {
        LOG_ERR("Timeout waiting for clear_dir");
        return -1;
    }
    clear_in_flight = false;
    if (resp.res) { LOG_ERR("clear_audio_directory failed: %d", resp.res); return -1; }
    return 0;
}

int save_offset(const char *filename, uint32_t offset)
{
    sd_req_t req = {0};
    req.type = REQ_SAVE_OFFSET;
    strncpy(req.u.info.offset_info.oldest_filename, filename, MAX_FILENAME_LEN - 1);
    req.u.info.offset_info.offset_in_file = offset;

    int ret = k_msgq_put(&sd_msgq, &req, K_NO_WAIT);
    if (ret) { LOG_ERR("Failed to queue save_offset: %d", ret); return -1; }
    return 0;
}

int get_offset(char *filename, uint32_t *offset)
{
    if (!filename || !offset) return -EINVAL;
    strncpy(filename, current_offset_info.oldest_filename, MAX_FILENAME_LEN - 1);
    filename[MAX_FILENAME_LEN - 1] = '\0';
    *offset = current_offset_info.offset_in_file;
    return 0;
}

int create_new_audio_file(void)
{
    static struct read_resp resp;
    static volatile bool create_in_flight;

    if (create_in_flight) {
        if (k_sem_take(&resp.sem, K_NO_WAIT) == 0) {
            create_in_flight = false;
        } else {
            LOG_WRN("create_new_audio_file: previous request still in-flight");
            return -EBUSY;
        }
    }
    create_in_flight = true;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_CREATE_NEW_FILE;
    req.u.create_file.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret) {
        LOG_ERR("Failed to queue create_new_audio_file: %d", ret);
        create_in_flight = false;
        return -1;
    }

    if (k_sem_take(&resp.sem, K_MSEC(15000)) != 0) {
        LOG_ERR("Timeout waiting for create_new_audio_file");
        return -1;
    }
    create_in_flight = false;
    if (resp.res) { LOG_ERR("create_new_audio_file failed: %d", resp.res); return -1; }

    if (ble_connected) ble_connect_time_ms = k_uptime_get();
    return 0;
}

int get_audio_file_stats(uint32_t *file_count, uint64_t *total_size)
{
    if (!file_count || !total_size) return -EINVAL;

    static struct file_stats_resp resp;
    static volatile bool stats_in_flight;

    if (stats_in_flight) {
        if (k_sem_take(&resp.sem, K_NO_WAIT) == 0) {
            stats_in_flight = false;
        } else {
            LOG_WRN("get_audio_file_stats: previous request still in-flight");
            return -EBUSY;
        }
    }
    stats_in_flight = true;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_GET_FILE_STATS;
    req.u.file_stats.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret) {
        LOG_ERR("Failed to queue get_file_stats: %d", ret);
        stats_in_flight = false;
        return -1;
    }

    if (k_sem_take(&resp.sem, K_MSEC(15000)) != 0) {
        LOG_ERR("Timeout waiting for get_file_stats");
        return -1;
    }
    stats_in_flight = false;
    if (resp.res) { LOG_ERR("get_audio_file_stats failed: %d", resp.res); return -1; }

    *file_count = resp.file_count;
    *total_size = resp.total_size;
    return 0;
}

int get_audio_file_list(char filenames[][MAX_FILENAME_LEN], int max_files, int *count)
{
    if (!filenames || !count || max_files <= 0) return -EINVAL;

    static struct file_list_resp resp;
    static volatile bool list_in_flight;

    if (list_in_flight) {
        if (k_sem_take(&resp.sem, K_NO_WAIT) == 0) {
            list_in_flight = false;
        } else {
            LOG_WRN("get_audio_file_list: previous request still in-flight");
            return -EBUSY;
        }
    }
    list_in_flight = true;
    k_sem_init(&resp.sem, 0, 1);
    resp.count = 0;

    sd_req_t req = {0};
    req.type = REQ_GET_FILE_LIST;
    req.u.file_list.filenames = filenames;
    req.u.file_list.sizes     = NULL;  /* no sizes requested */
    req.u.file_list.max_files = max_files;
    req.u.file_list.resp      = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret) {
        LOG_ERR("Failed to queue get_file_list: %d", ret);
        list_in_flight = false;
        return ret;
    }

    if (k_sem_take(&resp.sem, K_MSEC(15000)) != 0) {
        LOG_ERR("Timeout waiting for get_file_list");
        return -ETIMEDOUT;
    }
    list_in_flight = false;
    if (resp.res) { LOG_ERR("get_audio_file_list failed: %d", resp.res); return resp.res; }

    *count = resp.count;
    return 0;
}

int get_audio_file_list_with_sizes(char filenames[][MAX_FILENAME_LEN],
                                   uint32_t *sizes, int max_files, int *count)
{
    if (!filenames || !count || max_files <= 0) return -EINVAL;

    static struct file_list_resp resp;
    static volatile bool list_sizes_in_flight;

    if (list_sizes_in_flight) {
        if (k_sem_take(&resp.sem, K_NO_WAIT) == 0) {
            list_sizes_in_flight = false;
        } else {
            LOG_WRN("get_audio_file_list_with_sizes: previous request still in-flight");
            return -EBUSY;
        }
    }
    list_sizes_in_flight = true;
    k_sem_init(&resp.sem, 0, 1);
    resp.count = 0;

    sd_req_t req = {0};
    req.type = REQ_GET_FILE_LIST;
    req.u.file_list.filenames = filenames;
    req.u.file_list.sizes     = sizes;
    req.u.file_list.max_files = max_files;
    req.u.file_list.resp      = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret) {
        LOG_ERR("Failed to queue get_file_list: %d", ret);
        list_sizes_in_flight = false;
        return ret;
    }

    if (k_sem_take(&resp.sem, K_MSEC(15000)) != 0) {
        LOG_ERR("Timeout waiting for get_file_list");
        return -ETIMEDOUT;
    }
    list_sizes_in_flight = false;
    if (resp.res) { LOG_ERR("get_audio_file_list_with_sizes failed: %d", resp.res); return resp.res; }

    *count = resp.count;
    return 0;
}

