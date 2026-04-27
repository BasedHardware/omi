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

#include <ctype.h>
#include <errno.h>
#include <lfs.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/atomic.h>

#include "rtc.h"

LOG_MODULE_REGISTER(sd_card, CONFIG_LOG_DEFAULT_LEVEL);

#define DISK_DRIVE_NAME CONFIG_SDMMC_VOLUME_NAME
#define SD_REQ_QUEUE_MSGS 100
#define SD_FSYNC_INTERVAL_MS (60 * 1000)
#define WRITE_BATCH_COUNT 100
#define WRITE_DRAIN_BURST 16
#define ERROR_THRESHOLD 5
#define FILE_CACHE_TTL_MS (30 * 1000)
#define BOOT_MIN_AUDIO_FILE_SIZE 10000

/* LittleFS paths are relative to FS root (no mount-point prefix) */
#define FILE_DATA_DIR "audio"
#define FILE_INFO_PATH "info.txt"

/* ------------------------------------------------------------------ */
/* LittleFS state                                                     */
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
static struct lfs_file_config lfs_fdata_cfg = {.buffer = lfs_fdata_buf};
static struct lfs_file_config lfs_finfo_cfg = {.buffer = lfs_finfo_buf};

/* LFS I/O buffers — sized to cache_size (4096) for multi-sector I/O */
static uint8_t lfs_read_buf[4096];
static uint8_t lfs_prog_buf[4096];
/* Lookahead buffer sizing:
 * 128 bytes = 1024 blocks = 4 MB window → too small for 512 MB SD (128K blocks).
 * Every time the window is exhausted, LFS triggers a FULL filesystem traversal
 * (lfs_alloc_scan → lfs_fs_traverse_) which reads every block in every file.
 * With 200 MB of data (~50K blocks) this costs 10-50+ seconds per scan over SPI.
 *
 * 2048 bytes = 16384 blocks = 64 MB window → only ~8 scans to cover entire disk.
 * Reduces scan frequency from every ~4 MB written to every ~64 MB written.
 * Cost: 1920 bytes extra static RAM (nRF52840 has 256 KB). */
#define LFS_LOOKAHEAD_SIZE 2048
static uint8_t lfs_lookahead_buf[LFS_LOOKAHEAD_SIZE];

/* Shared temp sector buffer â€” only used from worker thread, safe as static */
static uint8_t _lfs_io_tmp[512];

/* ------------------------------------------------------------------ */
/* Disk sector size (always 512 for SD) */
#define DISK_SECTOR_SIZE 512
/* LFS block size: groups 8 sectors into one LFS block.
 * With 512-byte blocks, a 512 MB SD has 1M blocks and LFS metadata overhead
 * is enormous (CTZ skip-lists, lookahead scans).  4096-byte blocks reduce
 * the block count to ~128K and cut metadata overhead by ~8x. */
#define LFS_BLOCK_SIZE 4096
#define LFS_CACHE_SIZE LFS_BLOCK_SIZE                         /* cache = 1 full block for multi-sector I/O */
#define SECTORS_PER_BLOCK (LFS_BLOCK_SIZE / DISK_SECTOR_SIZE) /* 8 */
/* LittleFS disk_access callbacks                                      */
/* ------------------------------------------------------------------ */

/*
 * Map LFS (block, offset) to disk sector.
 *   LFS block N at byte offset K  →  disk sector  N * SECTORS_PER_BLOCK + K/512
 * With cache_size == 4096 (== block_size), LFS typically calls us with
 * size == 4096 and off == 0.  The fast path handles any aligned multi-sector
 * read in a single disk_access call (CMD18 multi-block read).
 */
static int lfs_disk_read_cb(const struct lfs_config *c, lfs_block_t block, lfs_off_t off, void *buffer, lfs_size_t size)
{
    (void) c;
    uint32_t sector = (uint32_t) block * SECTORS_PER_BLOCK + off / DISK_SECTOR_SIZE;
    uint32_t sec_off = off % DISK_SECTOR_SIZE;

    /* Fast path: aligned multi-sector read (the common case with cache_size=4096) */
    if (sec_off == 0 && (size % DISK_SECTOR_SIZE) == 0) {
        uint32_t nsec = size / DISK_SECTOR_SIZE;
        return disk_access_read(DISK_DRIVE_NAME, buffer, sector, nsec) == 0 ? LFS_ERR_OK : LFS_ERR_IO;
    }
    /* Generic path: partial / unaligned */
    uint8_t *dst = (uint8_t *) buffer;
    while (size > 0) {
        if (disk_access_read(DISK_DRIVE_NAME, _lfs_io_tmp, sector, 1) != 0)
            return LFS_ERR_IO;
        lfs_size_t chunk = DISK_SECTOR_SIZE - sec_off;
        if (chunk > size)
            chunk = size;
        memcpy(dst, _lfs_io_tmp + sec_off, chunk);
        dst += chunk;
        size -= chunk;
        sec_off = 0;
        sector++;
    }
    return LFS_ERR_OK;
}

static int
lfs_disk_prog_cb(const struct lfs_config *c, lfs_block_t block, lfs_off_t off, const void *buffer, lfs_size_t size)
{
    (void) c;
    uint32_t sector = (uint32_t) block * SECTORS_PER_BLOCK + off / DISK_SECTOR_SIZE;
    uint32_t sec_off = off % DISK_SECTOR_SIZE;

    /* Fast path: aligned multi-sector write (CMD25 multi-block write) */
    if (sec_off == 0 && (size % DISK_SECTOR_SIZE) == 0) {
        uint32_t nsec = size / DISK_SECTOR_SIZE;
        return disk_access_write(DISK_DRIVE_NAME, buffer, sector, nsec) == 0 ? LFS_ERR_OK : LFS_ERR_IO;
    }
    /* Generic path: read-modify-write per sector */
    const uint8_t *src = (const uint8_t *) buffer;
    while (size > 0) {
        if (disk_access_read(DISK_DRIVE_NAME, _lfs_io_tmp, sector, 1) != 0)
            return LFS_ERR_IO;
        lfs_size_t chunk = DISK_SECTOR_SIZE - sec_off;
        if (chunk > size)
            chunk = size;
        memcpy(_lfs_io_tmp + sec_off, src, chunk);
        if (disk_access_write(DISK_DRIVE_NAME, _lfs_io_tmp, sector, 1) != 0)
            return LFS_ERR_IO;
        src += chunk;
        size -= chunk;
        sec_off = 0;
        sector++;
    }
    return LFS_ERR_OK;
}

static int lfs_disk_erase_cb(const struct lfs_config *c, lfs_block_t block)
{
    /* SD card erases blocks internally on write â€” this is a true no-op. */
    (void) c;
    (void) block;
    return LFS_ERR_OK;
}

static int lfs_disk_sync_cb(const struct lfs_config *c)
{
    (void) c;
    (void) disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_SYNC, NULL);
    return LFS_ERR_OK;
}

/* LFS config â€” block_count filled at runtime from DISK_IOCTL_GET_SECTOR_COUNT */
static struct lfs_config lfs_cfg = {
    .read = lfs_disk_read_cb,
    .prog = lfs_disk_prog_cb,
    .erase = lfs_disk_erase_cb,
    .sync = lfs_disk_sync_cb,

    .read_size = DISK_SECTOR_SIZE,
    .prog_size = DISK_SECTOR_SIZE,
    .block_size = LFS_BLOCK_SIZE,
    .block_count = 0,                     /* set at mount time */
    .cache_size = LFS_CACHE_SIZE,         /* 4096: full-block cache → multi-sector I/O */
    .lookahead_size = LFS_LOOKAHEAD_SIZE, /* 2048 bytes = 16384 blocks = 64 MB window */

    .read_buffer = lfs_read_buf,
    .prog_buffer = lfs_prog_buf,
    .lookahead_buffer = lfs_lookahead_buf,

    /* SD card has internal wear leveling â†’ disable LFS wear leveling */
    .block_cycles = -1,

#if LFS_VERSION >= 0x00020009
    /* Disable metadata compaction during lfs_fs_gc() -- we only want
     * the allocator pre-warm (lookahead scan), not expensive compaction.
     * compact_thresh was added in LFS 2.9. */
    .compact_thresh = (lfs_size_t) -1,
#endif
};

/* ------------------------------------------------------------------ */
/* Batch write buffer & general state                                  */
/* ------------------------------------------------------------------ */

static uint8_t write_batch_buffer[WRITE_BATCH_COUNT * MAX_WRITE_SIZE];
static size_t write_batch_offset = 0;
static int write_batch_counter = 0;
static uint8_t writing_error_counter = 0;
static bool sd_write_blocked = false;
static int64_t last_write_blocked_log_ms = 0;
static uint32_t write_drop_packets = 0;
static uint32_t write_drop_bytes = 0;

/* SD boot readiness gate: cleared during init, set after pre-warm + file open.
 * write_to_file() silently discards data while this is 0, preventing the message
 * queue from filling up while lfs_fs_gc() is running on the worker thread. */
static atomic_t sd_boot_ready;

/* Deferred control requests when prio queue is temporarily saturated */
static atomic_t pending_flush_on_ble_connect;
static atomic_t pending_time_synced;
static uint32_t pending_time_synced_utc = 0;

static bool is_mounted = false;
static bool sd_enabled = false;
static bool sd_shutdown_in_progress = false;
static atomic_t sd_io_low_power = ATOMIC_INIT(0);
/* 1: supported/unknown, 0: unsupported (ENOSYS/ENOTSUP observed) */
static atomic_t sd_dev_pm_supported = ATOMIC_INIT(1);
static uint32_t current_file_size = 0;
static size_t bytes_since_sync = 0;
static int64_t last_file_sync_uptime_ms = 0;

/* Current writing file info */
static char current_filename[MAX_FILENAME_LEN] = {0};
static char current_file_path[64] = {0};
static int64_t current_file_created_uptime_ms = 0;
static bool current_file_needs_rename = false;
static bool deferred_timesync_rename_pending = false;
static uint32_t deferred_timesync_utc_time = 0;
static uint32_t cached_stats_file_count = 0;
static uint64_t cached_stats_total_size = 0;
static int64_t cached_stats_valid_until_ms = 0;
static bool file_cache_valid = false;
static int cached_file_list_count = 0;
static uint32_t cached_total_file_count = 0;
static uint64_t cached_total_file_size = 0;
static char cached_file_names[MAX_AUDIO_FILES][MAX_FILENAME_LEN] = {0};
static uint32_t cached_file_sizes[MAX_AUDIO_FILES] = {0};

/* BLE connection tracking for file rotation */
static bool ble_connected = false;
static int64_t ble_connect_time_ms = 0;

/* Track if active file was deleted while BLE connected */
static bool current_file_deleted = false;

/* Offset info (oldest file + byte offset) */
static sd_offset_info_t current_offset_info = {0};

/* Hardware device references */
static const struct device *const sd_dev = DEVICE_DT_GET(DT_NODELABEL(sdhc0));
static const struct gpio_dt_spec sd_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

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
static uint8_t lfs_read_handle_buf[4096];
static struct lfs_file_config lfs_read_handle_cfg = {.buffer = lfs_read_handle_buf};
static char read_handle_filename[MAX_FILENAME_LEN] = {0};
static bool read_handle_open = false;
static lfs_soff_t read_handle_pos = 0;

/* Sync generation: incremented every time lfs_fil_data is synced.
 * The read handle records which generation it was opened at;
 * if it doesn't match, the handle is stale (file grew) and must reopen. */
static uint32_t data_sync_gen = 0;
static uint32_t read_handle_gen = 0;

/* Forward declarations */
void sd_worker_thread(void);
static void process_write_data_req(const sd_req_t *req);
static int create_audio_file_with_timestamp(void);
static int flush_batch_buffer(void);
static bool should_rotate_file(void);
static void build_file_path(const char *filename, char *path, size_t path_size);
static void invalidate_file_cache(void);
static void update_current_file_cache_size(uint32_t delta);
static void sort_cached_file_entries(void);
static void sd_set_io_low_power(bool enable);

static void process_save_offset_req(const sd_req_t *req)
{
    if (sd_write_blocked)
        return;

    sd_set_io_low_power(false);
    lfs_file_seek(&lfs_fs, &lfs_fil_info, 0, LFS_SEEK_SET);
    lfs_ssize_t bw = lfs_file_write(&lfs_fs, &lfs_fil_info, &req->u.info.offset_info, sizeof(sd_offset_info_t));
    if (bw == (lfs_ssize_t) sizeof(sd_offset_info_t)) {
        lfs_file_sync(&lfs_fs, &lfs_fil_info);
        memcpy(&current_offset_info, &req->u.info.offset_info, sizeof(sd_offset_info_t));
    } else {
        LOG_ERR("[SD_WORK] save offset write err %d", (int) bw);
    }
    sd_set_io_low_power(true);
}

static void drain_pending_write_queue_for_shutdown(void)
{
    while (1) {
        sd_req_t pending_req;
        if (k_msgq_get(&sd_msgq, &pending_req, K_NO_WAIT) != 0) {
            break;
        }

        if (pending_req.type == REQ_WRITE_DATA) {
            process_write_data_req(&pending_req);
        } else if (pending_req.type == REQ_SAVE_OFFSET) {
            process_save_offset_req(&pending_req);
        }
    }
}

static void process_write_data_req(const sd_req_t *req)
{
    if (sd_write_blocked)
        return;
    if (current_file_deleted && ble_connected)
        return;

    /* Track whether we woke SPI for I/O in this call so we can
     * suspend it once at the end — keeps SPI + SD card powered
     * only during actual flash operations, not during the long
     * batch-accumulation window between flushes. */
    bool spi_woken = false;

    if (current_filename[0] == '\0') {
        sd_set_io_low_power(false);
        spi_woken = true;
        int res = create_audio_file_with_timestamp();
        if (res < 0) {
            sd_write_blocked = true;
            goto done;
        }
    }

    if (should_rotate_file()) {
        LOG_INF("[SD_WORK] Rotating file after 30 min");
        if (!spi_woken) { sd_set_io_low_power(false); spi_woken = true; }
        flush_batch_buffer();
        create_audio_file_with_timestamp();
    }

    if (write_batch_offset + req->u.write.len > sizeof(write_batch_buffer)) {
        if (!spi_woken) { sd_set_io_low_power(false); spi_woken = true; }
        flush_batch_buffer();
        if (write_batch_offset + req->u.write.len > sizeof(write_batch_buffer)) {
            LOG_ERR("[SD_WORK] batch buffer overflow guard len=%u off=%u",
                    (unsigned) req->u.write.len,
                    (unsigned) write_batch_offset);
            goto done;
        }
    }

    memcpy(write_batch_buffer + write_batch_offset, req->u.write.buf, req->u.write.len);
    write_batch_offset += req->u.write.len;
    write_batch_counter++;

    int queued_writes = k_msgq_num_used_get(&sd_msgq);
    bool queue_pressure_high = queued_writes >= (SD_REQ_QUEUE_MSGS / 3);

    if (write_batch_counter >= WRITE_BATCH_COUNT || queue_pressure_high) {
        if (!spi_woken) { sd_set_io_low_power(false); spi_woken = true; }
        flush_batch_buffer();
    }

    bool sync_due_to_interval =
        (bytes_since_sync > 0) && ((k_uptime_get() - last_file_sync_uptime_ms) >= SD_FSYNC_INTERVAL_MS);

    if (sync_due_to_interval) {
        if (!spi_woken) { sd_set_io_low_power(false); spi_woken = true; }
        lfs_file_sync(&lfs_fs, &lfs_fil_data);
        data_sync_gen++;
        bytes_since_sync = 0;
        last_file_sync_uptime_ms = k_uptime_get();
    }

done:
    if (spi_woken) {
        sd_set_io_low_power(true);
    }
}

static void close_read_handle(void)
{
    if (read_handle_open) {
        lfs_file_close(&lfs_fs, &lfs_read_handle);
        read_handle_open = false;
        read_handle_filename[0] = '\0';
        read_handle_pos = 0;
    }
}

static bool pm_action_is_unsupported(int ret)
{
    return (ret == -ENOSYS || ret == -ENOTSUP);
}

static bool pm_action_is_ok(int ret)
{
    return (ret == 0 || ret == -EALREADY || pm_action_is_unsupported(ret));
}

static void sd_set_io_low_power(bool enable)
{
    const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi3));

    if (!sd_enabled || !device_is_ready(spi_dev)) {
        return;
    }

    if (enable) {
        if (!atomic_cas(&sd_io_low_power, 0, 1)) {
            return;
        }

        int ret_sd = 0;
        if (atomic_get(&sd_dev_pm_supported)) {
            ret_sd = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_SUSPEND);
            if (pm_action_is_unsupported(ret_sd)) {
                atomic_set(&sd_dev_pm_supported, 0);
                LOG_INF("SD device PM suspend unsupported, keep using SPI PM only");
            }
        }
        int ret_spi = pm_device_action_run(spi_dev, PM_DEVICE_ACTION_SUSPEND);
        if (!pm_action_is_ok(ret_sd) || !pm_action_is_ok(ret_spi)) {
            LOG_WRN("SD low-power suspend failed (sd=%d spi=%d)", ret_sd, ret_spi);
        }
    } else {
        if (!atomic_cas(&sd_io_low_power, 1, 0)) {
            return;
        }

        int ret_spi = pm_device_action_run(spi_dev, PM_DEVICE_ACTION_RESUME);
        int ret_sd = 0;
        if (atomic_get(&sd_dev_pm_supported)) {
            ret_sd = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_RESUME);
            if (pm_action_is_unsupported(ret_sd)) {
                atomic_set(&sd_dev_pm_supported, 0);
                LOG_INF("SD device PM resume unsupported, keep using SPI PM only");
            }
        }
        if (!pm_action_is_ok(ret_sd) || !pm_action_is_ok(ret_spi)) {
            LOG_WRN("SD low-power resume failed (sd=%d spi=%d)", ret_sd, ret_spi);
        }
    }
}

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
            if (atomic_get(&sd_dev_pm_supported)) {
                int ret_sd = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_RESUME);
                if (pm_action_is_unsupported(ret_sd)) {
                    atomic_set(&sd_dev_pm_supported, 0);
                }
            }
        }
        atomic_set(&sd_io_low_power, 0);
        sd_enabled = true;
    } else {
        if (device_is_ready(spi_dev)) {
            if (atomic_get(&sd_dev_pm_supported)) {
                int ret_sd = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_SUSPEND);
                if (pm_action_is_unsupported(ret_sd)) {
                    atomic_set(&sd_dev_pm_supported, 0);
                }
            }
            pm_device_action_run(spi_dev, PM_DEVICE_ACTION_SUSPEND);
        }
        gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 11, GPIO_DISCONNECTED);
        ret = gpio_pin_set_dt(&sd_en, 0);
        atomic_set(&sd_io_low_power, 0);
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
    uint32_t sector_size = 0;
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
            break; /* init succeeded */
        }

        LOG_WRN("SD CTRL_INIT attempt %d/5 failed: %d", attempt, ret);
        (void) disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_DEINIT, NULL);
        sd_enable_power(false);
        k_msleep(50);
    }

    if (ret != 0) {
        LOG_ERR("Disk CTRL_INIT failed after retries: %d", ret);
        return ret;
    }

    disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_GET_SECTOR_COUNT, &sector_count);
    disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_GET_SECTOR_SIZE, &sector_size);

    /* LittleFS only needs the disk to be 'initialised' from here on;
     * keep driver active (no CTRL_DEINIT) so callbacks work. */
    LOG_INF("SD: %u sectors x %u bytes = %u MB",
            sector_count,
            sector_size,
            (unsigned) ((uint64_t) sector_count * sector_size >> 20));

    /* read/prog stay at sector granularity (512);
     * cache = full block (4096) for multi-sector I/O. */
    uint32_t ss = (sector_size > 0) ? sector_size : DISK_SECTOR_SIZE;
    lfs_cfg.read_size = ss;
    lfs_cfg.prog_size = ss;
    lfs_cfg.cache_size = LFS_CACHE_SIZE;
    lfs_cfg.block_size = LFS_BLOCK_SIZE;
    lfs_cfg.block_count = sector_count / (LFS_BLOCK_SIZE / ss);

    /* Try to mount existing filesystem */
    int64_t mount_start_ms = k_uptime_get();
    ret = lfs_mount(&lfs_fs, &lfs_cfg);
    LOG_INF("[SD_BOOT] lfs_mount took %lld ms (ret=%d)", k_uptime_get() - mount_start_ms, ret);
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
    LOG_INF("LittleFS mounted OK (block_size=%u, block_count=%u, lookahead=%u bytes = %u blocks window)",
            (unsigned) lfs_cfg.block_size,
            (unsigned) lfs_cfg.block_count,
            (unsigned) lfs_cfg.lookahead_size,
            (unsigned) lfs_cfg.lookahead_size * 8);
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
    if (!a || !b)
        return false;
    for (size_t i = 0; i < MAX_FILENAME_LEN; i++) {
        if (tolower((unsigned char) a[i]) != tolower((unsigned char) b[i]))
            return false;
        if (a[i] == '\0' || b[i] == '\0')
            break;
    }
    return true;
}

static void cleanup_audio_files_at_boot(void)
{
    uint32_t removed_total = 0;
    uint32_t removed_tmp = 0;
    uint32_t removed_small = 0;

    while (1) {
        lfs_dir_t dir;
        struct lfs_info info;
        char target_name[MAX_FILENAME_LEN] = {0};
        bool target_is_tmp = false;
        bool target_is_small = false;

        if (lfs_dir_open(&lfs_fs, &dir, FILE_DATA_DIR) < 0) {
            break;
        }

        while (lfs_dir_read(&lfs_fs, &dir, &info) > 0) {
            if (info.type != LFS_TYPE_REG) {
                continue;
            }

            char *dot = strrchr(info.name, '.');
            if (!dot || strcasecmp(dot, ".txt") != 0) {
                continue;
            }

            bool is_tmp = (strncasecmp(info.name, "TMP_", 4) == 0);
            bool is_small = (info.size < BOOT_MIN_AUDIO_FILE_SIZE);
            if (!is_tmp && !is_small) {
                continue;
            }

            strncpy(target_name, info.name, sizeof(target_name) - 1);
            target_is_tmp = is_tmp;
            target_is_small = is_small;
            break;
        }

        lfs_dir_close(&lfs_fs, &dir);

        if (target_name[0] == '\0') {
            break;
        }

        char path[64];
        build_file_path(target_name, path, sizeof(path));
        int rm = lfs_remove(&lfs_fs, path);
        if (rm < 0) {
            LOG_WRN("[SD_BOOT] cleanup rm %s failed: %d", path, rm);
            continue;
        }

        removed_total++;
        if (target_is_tmp) {
            removed_tmp++;
        }
        if (target_is_small) {
            removed_small++;
        }
    }

    if (removed_total > 0) {
        LOG_INF("[SD_BOOT] cleanup removed %u file(s) (tmp=%u, small<%uB=%u)",
                removed_total,
                removed_tmp,
                BOOT_MIN_AUDIO_FILE_SIZE,
                removed_small);
        invalidate_file_cache();
    }
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

    /* Clear file cache arrays before populating */
    memset(cached_file_names, 0, sizeof(cached_file_names));
    memset(cached_file_sizes, 0, sizeof(cached_file_sizes));
    int list_count = 0;

    LOG_INF("========== AUDIO FILES ON SD CARD ==========");
    while (lfs_dir_read(&lfs_fs, &dir, &info) > 0) {
        if (info.type != LFS_TYPE_REG)
            continue;
        char *dot = strrchr(info.name, '.');
        if (dot && strcasecmp(dot, ".txt") == 0) {
            LOG_INF("  [%u] %s - %u bytes", file_count + 1, info.name, (unsigned) info.size);
            total_size += info.size;
            file_count++;
            /* Also populate the file list cache so that get_file_list
             * can return data immediately during the long gc pre-warm. */
            if (list_count < MAX_AUDIO_FILES) {
                strncpy(cached_file_names[list_count], info.name, MAX_FILENAME_LEN - 1);
                cached_file_names[list_count][MAX_FILENAME_LEN - 1] = '\0';
                cached_file_sizes[list_count] = (uint32_t) info.size;
                list_count++;
            }
        }
    }
    lfs_dir_close(&lfs_fs, &dir);
    cached_file_list_count = list_count;
    sort_cached_file_entries();
    cached_stats_file_count = file_count;
    cached_stats_total_size = total_size;
    cached_stats_valid_until_ms = k_uptime_get() + FILE_CACHE_TTL_MS;
    cached_total_file_count = file_count;
    cached_total_file_size = total_size;
    file_cache_valid = true;
    LOG_INF("[SD_BOOT] %u files, %u bytes total", file_count, (unsigned) total_size);
    LOG_INF("=============================================");
}

/* ------------------------------------------------------------------ */
/* File creation / continuation at boot                               */
/* ------------------------------------------------------------------ */

#define FILE_CONTINUE_THRESHOLD_SEC (60)

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

    char latest_filename[MAX_FILENAME_LEN] = {0};
    uint32_t latest_timestamp = 0;

    while (lfs_dir_read(&lfs_fs, &dir, &info) > 0) {
        if (info.type != LFS_TYPE_REG)
            continue;
        char *dot = strrchr(info.name, '.');
        if (dot && strcasecmp(dot, ".txt") == 0) {
            uint32_t ts = (uint32_t) strtoul(info.name, NULL, 16);
            if (ts > latest_timestamp) {
                latest_timestamp = ts;
                strncpy(latest_filename, info.name, sizeof(latest_filename) - 1);
            }
        }
    }
    lfs_dir_close(&lfs_fs, &dir);

    if (latest_filename[0] == '\0')
        return -1;

    int32_t diff = (int32_t) (current_time - latest_timestamp);
    LOG_INF("[SD_BOOT] Latest file: %s diff=%d s", latest_filename, diff);

    if (diff < 0 || diff > FILE_CONTINUE_THRESHOLD_SEC)
        return -1;

    strncpy(current_filename, latest_filename, sizeof(current_filename) - 1);
    build_file_path(current_filename, current_file_path, sizeof(current_file_path));

    int ret = lfs_file_opencfg(&lfs_fs, &lfs_fil_data, current_file_path, LFS_O_RDWR | LFS_O_APPEND, &lfs_fdata_cfg);
    if (ret < 0) {
        LOG_ERR("[SD_BOOT] open existing file failed: %d", ret);
        current_filename[0] = '\0';
        return -1;
    }

    current_file_size = (uint32_t) lfs_file_size(&lfs_fs, &lfs_fil_data);
    bytes_since_sync = 0;
    write_batch_offset = 0;
    write_batch_counter = 0;
    last_file_sync_uptime_ms = k_uptime_get();
    current_file_created_uptime_ms = k_uptime_get();
    current_file_needs_rename = false;

    LOG_INF("[SD_BOOT] Continuing file: %s (%u bytes)", current_filename, current_file_size);
    return 0;
}

static int create_audio_file_with_timestamp(void)
{
    bool rtc_valid = rtc_is_valid();
    uint32_t timestamp = 0;

    if (rtc_valid) {
        timestamp = get_utc_time();
        if (timestamp == 0 || timestamp < 1700000000U)
            rtc_valid = false;
    }

    /* Close current file if open */
    if (current_filename[0] != '\0') {
        if (write_batch_offset > 0)
            flush_batch_buffer();
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
        uint32_t boot_tag = (uint32_t) k_uptime_get_32();
        uint32_t cycle_tag = (uint32_t) k_cycle_get_32();
        snprintf(current_filename, sizeof(current_filename), "TMP_%08X_%04X.txt", boot_tag, cycle_tag & 0xFFFFU);
        current_file_needs_rename = true;
        LOG_WRN("RTC not synced, temp file: %s", current_filename);
    }

    build_file_path(current_filename, current_file_path, sizeof(current_file_path));
    LOG_INF("Creating audio file: %s", current_file_path);

    int ret = lfs_file_opencfg(
        &lfs_fs, &lfs_fil_data, current_file_path, LFS_O_CREAT | LFS_O_RDWR | LFS_O_APPEND, &lfs_fdata_cfg);
    if (ret < 0) {
        LOG_ERR("Failed to create %s: %d", current_file_path, ret);
        current_filename[0] = '\0';
        current_file_path[0] = '\0';
        return ret;
    }

    current_file_size = 0;
    bytes_since_sync = 0;
    write_batch_offset = 0;
    write_batch_counter = 0;
    writing_error_counter = 0;
    sd_write_blocked = false;
    last_file_sync_uptime_ms = k_uptime_get();
    current_file_created_uptime_ms = k_uptime_get();

    LOG_INF("Audio file created: %s", current_filename);
    invalidate_file_cache();
    return 0;
}

/* ------------------------------------------------------------------ */
/* Batch buffer flush                                                  */
/* ------------------------------------------------------------------ */

static int flush_batch_buffer(void)
{
    if (write_batch_offset == 0)
        return 0;

    if (sd_write_blocked) {
        write_batch_offset = 0;
        write_batch_counter = 0;
        return -EIO;
    }

    int64_t flush_start_ms = k_uptime_get();
    lfs_ssize_t bw = lfs_file_write(&lfs_fs, &lfs_fil_data, write_batch_buffer, write_batch_offset);
    int64_t flush_cost_ms = k_uptime_get() - flush_start_ms;
    if (flush_cost_ms > 2000) {
        LOG_WRN("[SD_PERF] flush_batch_buffer took %lld ms (wrote %u bytes, batch=%d)",
                flush_cost_ms,
                (unsigned) write_batch_offset,
                write_batch_counter);
    }
    if (bw < 0 || (size_t) bw != write_batch_offset) {
        writing_error_counter++;
        LOG_ERR("batch write error bw=%d wanted=%u", (int) bw, (unsigned) write_batch_offset);

        if (writing_error_counter > ERROR_THRESHOLD) {
            sd_write_blocked = true;
            LOG_ERR("Too many write errors, blocking write queue");
        }
        write_batch_offset = 0;
        write_batch_counter = 0;
        return -EIO;
    }

    bytes_since_sync += (size_t) bw;
    current_file_size += (uint32_t) bw;
    update_current_file_cache_size((uint32_t) bw);
    LOG_DBG("[SD] wrote %u bytes -> %s (total=%u)", (unsigned) bw, current_filename, current_file_size);
    write_batch_offset = 0;
    write_batch_counter = 0;
    writing_error_counter = 0;
    return 0;
}

/* ------------------------------------------------------------------ */
/* File rotation helper                                                */
/* ------------------------------------------------------------------ */

static bool should_rotate_file(void)
{
    if (current_file_created_uptime_ms == 0)
        return false;
    return (k_uptime_get() - current_file_created_uptime_ms) >= FILE_ROTATION_INTERVAL_MS;
}

/* ------------------------------------------------------------------ */
/* Filename sort (hex timestamp, oldest first)                        */
/* ------------------------------------------------------------------ */

static int compare_filenames(const void *a, const void *b)
{
    uint32_t ta = (uint32_t) strtoul((const char *) a, NULL, 16);
    uint32_t tb = (uint32_t) strtoul((const char *) b, NULL, 16);
    return (ta < tb) ? -1 : (ta > tb) ? 1 : 0;
}

static void invalidate_file_cache(void)
{
    file_cache_valid = false;
    cached_stats_valid_until_ms = 0;
}

static void sort_cached_file_entries(void)
{
    if (cached_file_list_count <= 1) {
        return;
    }

    for (int i = 1; i < cached_file_list_count; i++) {
        char tmp_name[MAX_FILENAME_LEN] = {0};
        uint32_t tmp_size = cached_file_sizes[i];
        strncpy(tmp_name, cached_file_names[i], MAX_FILENAME_LEN - 1);

        int j = i - 1;
        while (j >= 0 && compare_filenames(cached_file_names[j], tmp_name) > 0) {
            strncpy(cached_file_names[j + 1], cached_file_names[j], MAX_FILENAME_LEN);
            cached_file_sizes[j + 1] = cached_file_sizes[j];
            j--;
        }

        strncpy(cached_file_names[j + 1], tmp_name, MAX_FILENAME_LEN);
        cached_file_sizes[j + 1] = tmp_size;
    }
}

static void update_current_file_cache_size(uint32_t delta)
{
    if (!file_cache_valid || delta == 0 || current_filename[0] == '\0') {
        return;
    }

    cached_total_file_size += delta;
    cached_stats_total_size = cached_total_file_size;
    cached_stats_file_count = cached_total_file_count;
    cached_stats_valid_until_ms = k_uptime_get() + FILE_CACHE_TTL_MS;

    for (int i = 0; i < cached_file_list_count; i++) {
        if (strcmp(cached_file_names[i], current_filename) == 0) {
            cached_file_sizes[i] += delta;
            return;
        }
    }

    /* Cache became stale (e.g. filename not indexed due truncation). */
    invalidate_file_cache();
}

static int refresh_file_cache(void)
{
    if (!is_mounted) {
        return -ENODEV;
    }

    lfs_dir_t dir;
    struct lfs_info info;
    int list_count = 0;
    uint32_t total_count = 0;
    uint64_t total_size = 0;

    memset(cached_file_names, 0, sizeof(cached_file_names));
    memset(cached_file_sizes, 0, sizeof(cached_file_sizes));

    int dres = lfs_dir_open(&lfs_fs, &dir, FILE_DATA_DIR);
    if (dres < 0) {
        if (dres == LFS_ERR_NOENT) {
            cached_file_list_count = 0;
            cached_total_file_count = 0;
            cached_total_file_size = 0;
            cached_stats_file_count = 0;
            cached_stats_total_size = 0;
            cached_stats_valid_until_ms = k_uptime_get() + FILE_CACHE_TTL_MS;
            file_cache_valid = true;
            return 0;
        }
        return dres;
    }

    while (lfs_dir_read(&lfs_fs, &dir, &info) > 0) {
        if (info.type != LFS_TYPE_REG) {
            continue;
        }

        char *dot = strrchr(info.name, '.');
        if (!dot || strcasecmp(dot, ".txt") != 0) {
            continue;
        }

        total_count++;
        total_size += info.size;

        if (list_count < MAX_AUDIO_FILES) {
            strncpy(cached_file_names[list_count], info.name, MAX_FILENAME_LEN - 1);
            cached_file_names[list_count][MAX_FILENAME_LEN - 1] = '\0';
            cached_file_sizes[list_count] = (uint32_t) info.size;
            list_count++;
        }
    }
    lfs_dir_close(&lfs_fs, &dir);

    cached_file_list_count = list_count;
    sort_cached_file_entries();

    if (current_filename[0] != '\0') {
        for (int i = 0; i < cached_file_list_count; i++) {
            if (strcmp(cached_file_names[i], current_filename) == 0) {
                total_size = total_size - cached_file_sizes[i] + current_file_size;
                cached_file_sizes[i] = current_file_size;
                break;
            }
        }
    }

    cached_total_file_count = total_count;
    cached_total_file_size = total_size;
    cached_stats_file_count = total_count;
    cached_stats_total_size = total_size;
    cached_stats_valid_until_ms = k_uptime_get() + FILE_CACHE_TTL_MS;
    file_cache_valid = true;

    return 0;
}

static int ensure_file_cache(void)
{
    if (file_cache_valid) {
        return 0;
    }
    return refresh_file_cache();
}

/* ------------------------------------------------------------------ */
/* Filename rename after time-sync                                     */
/* ------------------------------------------------------------------ */

void sd_update_filename_after_timesync(uint32_t synced_utc_time)
{
    if (!current_file_needs_rename || current_filename[0] == '\0' || !is_mounted)
        return;

    int64_t now_ms = k_uptime_get();
    uint32_t elapsed = (uint32_t) (now_ms - current_file_created_uptime_ms);
    uint32_t correct_ts = synced_utc_time - (elapsed / 1000U);

    char new_filename[MAX_FILENAME_LEN];
    snprintf(new_filename, sizeof(new_filename), "%08X.txt", correct_ts);
    LOG_INF("Rename: %s -> %s (elapsed=%u ms)", current_filename, new_filename, elapsed);

    if (write_batch_offset > 0)
        flush_batch_buffer();
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
        lfs_file_opencfg(&lfs_fs, &lfs_fil_data, current_file_path, LFS_O_RDWR | LFS_O_APPEND, &lfs_fdata_cfg);
        return;
    }

    strncpy(current_filename, new_filename, sizeof(current_filename) - 1);
    strncpy(current_file_path, new_path, sizeof(current_file_path) - 1);
    current_file_needs_rename = false;

    lfs_file_opencfg(&lfs_fs, &lfs_fil_data, current_file_path, LFS_O_RDWR | LFS_O_APPEND, &lfs_fdata_cfg);
    LOG_INF("File renamed OK: %s", current_filename);
}

/* ------------------------------------------------------------------ */
/* Worker thread & task definitions                                    */
/* ------------------------------------------------------------------ */

#define SD_WORKER_STACK_SIZE 16384
#define SD_WORKER_PRIORITY 7
K_THREAD_STACK_DEFINE(sd_worker_stack, SD_WORKER_STACK_SIZE);
static struct k_thread sd_worker_thread_data;
static k_tid_t sd_worker_tid = NULL;

/* ------------------------------------------------------------------ */
/* Internal helpers: file list, file stats                            */
/* ------------------------------------------------------------------ */

static int get_audio_file_list_internal(char filenames[][MAX_FILENAME_LEN], uint32_t *sizes, int max_files, int *count)
{
    if (!filenames || !count || max_files <= 0)
        return -EINVAL;
    if (!is_mounted)
        return -ENODEV;

    int cache_res = ensure_file_cache();
    if (cache_res < 0) {
        return cache_res;
    }

    int file_count = cached_file_list_count;
    if (file_count > max_files) {
        file_count = max_files;
    }

    for (int i = 0; i < file_count; i++) {
        strncpy(filenames[i], cached_file_names[i], MAX_FILENAME_LEN - 1);
        filenames[i][MAX_FILENAME_LEN - 1] = '\0';
        if (sizes) {
            sizes[i] = cached_file_sizes[i];
        }
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

    /* ---- Boot cleanup: remove stale temp/small files ---- */
    cleanup_audio_files_at_boot();

    /* ---- Print existing files at boot ---- */
    print_audio_files_at_boot();

    /* ---- Pre-warm LFS block allocator ---- */
    /* After mount, the LFS lookahead buffer is EMPTY and the start position
     * is random (seed % block_count).  The very first lfs_alloc() would
     * trigger lfs_alloc_scan() — a full O(used_blocks) filesystem traversal
     * over SPI SD that can take 10-50+ seconds with 100-200 MB of data.
     *
     * By calling lfs_fs_gc() here (with compact_thresh=-1 so it skips
     * metadata compaction), we force that expensive scan to happen NOW,
     * during boot init, BEFORE the audio pipeline starts feeding data.
     * This moves the latency spike from the real-time write path to a
     * one-time boot cost where dropping audio is acceptable. */
    {
        int64_t gc_start_ms = k_uptime_get();
        LOG_INF("[SD_BOOT] Pre-warming LFS allocator (lookahead=%u bytes, %u blocks window)...",
                LFS_LOOKAHEAD_SIZE,
                LFS_LOOKAHEAD_SIZE * 8);
        int gc_res = lfs_fs_gc(&lfs_fs);
        int64_t gc_elapsed_ms = k_uptime_get() - gc_start_ms;
        if (gc_res < 0) {
            LOG_WRN("[SD_BOOT] lfs_fs_gc failed: %d (took %lld ms)", gc_res, gc_elapsed_ms);
        } else {
            LOG_INF("[SD_BOOT] LFS allocator pre-warmed OK in %lld ms", gc_elapsed_ms);
        }
    }

    /* ---- Open / create info file ---- */
    {
        struct lfs_info info_lstat;
        bool info_exists = (lfs_stat(&lfs_fs, FILE_INFO_PATH, &info_lstat) == 0);
        bool need_init_off = !info_exists || (info_lstat.size < sizeof(sd_offset_info_t));

        res = lfs_file_opencfg(&lfs_fs, &lfs_fil_info, FILE_INFO_PATH, LFS_O_CREAT | LFS_O_RDWR, &lfs_finfo_cfg);
        if (res < 0) {
            LOG_ERR("[SD_WORK] open info failed: %d", res);
            sd_write_blocked = true;
        } else if (need_init_off) {
            memset(&current_offset_info, 0, sizeof(current_offset_info));
            lfs_ssize_t bw = lfs_file_write(&lfs_fs, &lfs_fil_info, &current_offset_info, sizeof(current_offset_info));
            if (bw != (lfs_ssize_t) sizeof(current_offset_info)) {
                LOG_ERR("[SD_WORK] init info write failed: %d", (int) bw);
            } else {
                lfs_file_sync(&lfs_fs, &lfs_fil_info);
            }
        } else {
            lfs_file_seek(&lfs_fs, &lfs_fil_info, 0, LFS_SEEK_SET);
            lfs_ssize_t rb = lfs_file_read(&lfs_fs, &lfs_fil_info, &current_offset_info, sizeof(current_offset_info));
            if (rb != (lfs_ssize_t) sizeof(current_offset_info)) {
                LOG_ERR("[SD_WORK] read offset info failed: %d", (int) rb);
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

    /* ---- SD boot init complete, allow writes ---- */
    atomic_set(&sd_boot_ready, 1);
    LOG_INF("[SD_BOOT] SD card ready for audio writes (boot took %lld ms)", k_uptime_get());

    /* Suspend SPI + SD until the first batch flush actually needs I/O.
     * Saves ~0.5 mA idle current during the initial accumulation window. */
    sd_set_io_low_power(true);

    /* ---- Main loop ---- */
    while (1) {
        /* Handle deferred control requests first (when queue was saturated). */
        if (atomic_cas(&pending_flush_on_ble_connect, 1, 0)) {
            req.type = REQ_FLUSH_FILE;
            req.u.create_file.resp = NULL;
            goto handle_req;
        }
        if (atomic_cas(&pending_time_synced, 1, 0)) {
            req.type = REQ_TIME_SYNCED;
            req.u.time_synced.utc_time = pending_time_synced_utc;
            goto handle_req;
        }

        /* Priority queue first: reads, flush, file-list, delete, etc.
         * These never wait behind pending audio writes. */
        if (k_msgq_get(&sd_prio_msgq, &req, K_NO_WAIT) == 0) {
            goto handle_req;
        }

        /* Regular write queue timeout: short when BLE connected (keep read/sync responsive),
         * long when offline (save power). */
        k_timeout_t write_wait = ble_connected ? K_MSEC(50) : K_MSEC(2000);
        if (k_msgq_get(&sd_msgq, &req, write_wait) != 0)
            continue;

    handle_req:
        /* Wake SPI for request types that need filesystem I/O.
         * REQ_WRITE_DATA manages its own SPI gating internally
         * (only wakes when a batch flush actually occurs). */
        if (req.type != REQ_WRITE_DATA) {
            sd_set_io_low_power(false);
        }

        switch (req.type) {

        /* ---- Write data ---- */
        case REQ_WRITE_DATA:
            process_write_data_req(&req);

            /* Drain additional queued write/save_offset messages in one pass.
             * This reduces queue churn and improves effective SD throughput. */
            for (int i = 0; i < WRITE_DRAIN_BURST; i++) {
                if (k_msgq_num_used_get(&sd_prio_msgq) > 0) {
                    break;
                }
                sd_req_t next_req;
                if (k_msgq_get(&sd_msgq, &next_req, K_NO_WAIT) != 0) {
                    break;
                }
                if (next_req.type == REQ_WRITE_DATA) {
                    process_write_data_req(&next_req);
                } else if (next_req.type == REQ_SAVE_OFFSET) {
                    process_save_offset_req(&next_req);
                }
            }
            break;

        /* ---- Read audio data (uses persistent file handle) ---- */
        case REQ_READ_DATA: {
            char read_path[64];
            build_file_path(req.u.read.filename, read_path, sizeof(read_path));

            bool is_active_file = (current_filename[0] != '\0' && strcmp(req.u.read.filename, current_filename) == 0);

            /* Close handle if different file requested */
            if (read_handle_open && strcmp(read_handle_filename, req.u.read.filename) != 0) {
                close_read_handle();
            }

            /* Reopen if handle is stale (file was synced since handle opened) */
            if (read_handle_open && read_handle_gen != data_sync_gen) {
                close_read_handle();
            }

            /* Open file if not already open */
            if (!read_handle_open) {
                res = lfs_file_opencfg(&lfs_fs, &lfs_read_handle, read_path, LFS_O_RDONLY, &lfs_read_handle_cfg);
                if (res < 0) {
                    LOG_ERR("[SD_WORK] open read failed: %s err=%d", read_path, res);
                    if (req.u.read.resp) {
                        req.u.read.resp->res = res;
                        req.u.read.resp->read_bytes = 0;
                        k_sem_give(&req.u.read.resp->sem);
                    }
                    break;
                }
                strncpy(read_handle_filename, req.u.read.filename, MAX_FILENAME_LEN - 1);
                read_handle_open = true;
                read_handle_pos = 0;
                read_handle_gen = data_sync_gen;
            }

            /* Only seek if position doesn't match (sequential reads skip seek) */
            if (read_handle_pos != (lfs_soff_t) req.u.read.offset) {
                lfs_file_seek(&lfs_fs, &lfs_read_handle, (lfs_soff_t) req.u.read.offset, LFS_SEEK_SET);
                read_handle_pos = (lfs_soff_t) req.u.read.offset;
            }

            lfs_ssize_t br = lfs_file_read(&lfs_fs, &lfs_read_handle, req.u.read.out_buf, req.u.read.length);

            /* Lazy sync: if we got 0 bytes (EOF) on the active file and
             * there is uncommitted data, flush+sync now and retry once.
             * This avoids the expensive lfs_file_sync on EVERY read
             * (was ~50-100 ms each) — we only pay the cost when we
             * actually hit the stale-EOF boundary. */
            if (br == 0 && is_active_file && (write_batch_offset > 0 || bytes_since_sync > 0)) {
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
                res = lfs_file_opencfg(&lfs_fs, &lfs_read_handle, read_path, LFS_O_RDONLY, &lfs_read_handle_cfg);
                if (res < 0) {
                    if (req.u.read.resp) {
                        req.u.read.resp->res = res;
                        req.u.read.resp->read_bytes = 0;
                        k_sem_give(&req.u.read.resp->sem);
                    }
                    break;
                }
                strncpy(read_handle_filename, req.u.read.filename, MAX_FILENAME_LEN - 1);
                read_handle_open = true;
                read_handle_pos = 0;
                read_handle_gen = data_sync_gen;

                lfs_file_seek(&lfs_fs, &lfs_read_handle, (lfs_soff_t) req.u.read.offset, LFS_SEEK_SET);
                read_handle_pos = (lfs_soff_t) req.u.read.offset;

                br = lfs_file_read(&lfs_fs, &lfs_read_handle, req.u.read.out_buf, req.u.read.length);
            }

            if (br > 0) {
                read_handle_pos += br;
            }

            if (req.u.read.resp) {
                req.u.read.resp->res = (br < 0) ? (int) br : 0;
                req.u.read.resp->read_bytes = (br < 0) ? 0 : (int) br;
                k_sem_give(&req.u.read.resp->sem);
            }
            break;
        }

        /* ---- Save offset ---- */
        case REQ_SAVE_OFFSET:
            process_save_offset_req(&req);
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
                    if (info.type != LFS_TYPE_REG)
                        continue;
                    build_file_path(info.name, fpath, sizeof(fpath));
                    int rm = lfs_remove(&lfs_fs, fpath);
                    if (rm < 0)
                        LOG_ERR("[SD_WORK] rm %s: %d", fpath, rm);
                }
                lfs_dir_close(&lfs_fs, &dir);
            }

            /* Reset offset info */
            memset(&current_offset_info, 0, sizeof(current_offset_info));
            lfs_file_seek(&lfs_fs, &lfs_fil_info, 0, LFS_SEEK_SET);
            lfs_file_write(&lfs_fs, &lfs_fil_info, &current_offset_info, sizeof(current_offset_info));
            lfs_file_sync(&lfs_fs, &lfs_fil_info);
            invalidate_file_cache();

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
            res = ensure_file_cache();

            if (req.u.file_stats.resp) {
                req.u.file_stats.resp->res = res;
                req.u.file_stats.resp->file_count = (res == 0) ? cached_total_file_count : 0;
                req.u.file_stats.resp->total_size = (res == 0) ? cached_total_file_size : 0;
                k_sem_give(&req.u.file_stats.resp->sem);
            }
            break;
        }

        /* ---- Get file list ---- */
        case REQ_GET_FILE_LIST: {
            int list_count = 0;
            res = get_audio_file_list_internal(
                req.u.file_list.filenames, req.u.file_list.sizes, req.u.file_list.max_files, &list_count);
            if (req.u.file_list.resp) {
                req.u.file_list.resp->res = res;
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
                        LOG_INF("[SD_WORK] Flushed %s (%u bytes)", current_filename, current_file_size);
                    }
                }
            }
            if (req.u.create_file.resp) {
                req.u.create_file.resp->res = flush_res;
                k_sem_give(&req.u.create_file.resp->sem);
            }
            break;
        }

        /* ---- Unmount SD/LFS (must run on worker thread) ---- */
        case REQ_UNMOUNT: {
            /* Shutdown path: stop accepting new writes and drain queued writes
             * so data already enqueued by mic thread is persisted before unmount. */
            drain_pending_write_queue_for_shutdown();
            int off_res = sd_unmount();
            if (req.u.create_file.resp) {
                req.u.create_file.resp->res = off_res;
                k_sem_give(&req.u.create_file.resp->sem);
            }
            break;
        }

        /* ---- Delete file ---- */
        case REQ_DELETE_FILE: {
            char del_path[64];
            build_file_path(req.u.delete_file.filename, del_path, sizeof(del_path));

            /* Close read handle if we're about to delete the file being read */
            if (read_handle_open && filename_equals_ignore_case(read_handle_filename, req.u.delete_file.filename)) {
                close_read_handle();
            }

            if (current_filename[0] != '\0' &&
                filename_equals_ignore_case(current_filename, req.u.delete_file.filename)) {
                LOG_INF("[SD_WORK] Deleting active recording file");
                flush_batch_buffer();
                lfs_file_close(&lfs_fs, &lfs_fil_data);
                current_filename[0] = '\0';
                current_file_path[0] = '\0';
                current_file_size = 0;
                bytes_since_sync = 0;
                last_file_sync_uptime_ms = 0;
                write_batch_offset = 0;
                write_batch_counter = 0;
                current_file_deleted = true;
            }

            int rm = lfs_remove(&lfs_fs, del_path);
            if (rm < 0 && rm != LFS_ERR_NOENT) {
                LOG_ERR("[SD_WORK] remove %s failed: %d", del_path, rm);
            } else {
                invalidate_file_cache();
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
                if (ble_connected) {
                    deferred_timesync_rename_pending = true;
                    deferred_timesync_utc_time = req.u.time_synced.utc_time;
                    LOG_INF("[SD_WORK] Deferring TMP rename while BLE connected");
                } else {
                    sd_update_filename_after_timesync(req.u.time_synced.utc_time);
                    invalidate_file_cache();
                    deferred_timesync_rename_pending = false;
                }
            } else if (current_filename[0] == '\0') {
                res = create_audio_file_with_timestamp();
                if (res < 0)
                    LOG_ERR("[SD_WORK] create after time sync failed: %d", res);
            }
            break;

        default:
            LOG_ERR("[SD_WORK] unknown request type %d", req.type);
        }

        /* Suspend SPI after non-write requests complete */
        if (req.type != REQ_WRITE_DATA) {
            sd_set_io_low_power(true);
        }
    }
}

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */

int app_sd_init(void)
{
    sd_shutdown_in_progress = false;
    if (!sd_worker_tid) {
        sd_worker_tid = k_thread_create(&sd_worker_thread_data,
                                        sd_worker_stack,
                                        SD_WORKER_STACK_SIZE,
                                        (k_thread_entry_t) sd_worker_thread,
                                        NULL,
                                        NULL,
                                        NULL,
                                        SD_WORKER_PRIORITY,
                                        0,
                                        K_NO_WAIT);
        k_thread_name_set(sd_worker_tid, "sd_worker");
    }
    return 0;
}

int app_sd_off(void)
{
    sd_shutdown_in_progress = true;
    bool unmount_completed = false;

    if (is_mounted && sd_worker_tid) {
        struct read_resp resp;
        k_sem_init(&resp.sem, 0, 1);
        resp.res = 0;

        sd_req_t req = {0};
        req.type = REQ_UNMOUNT;
        req.u.create_file.resp = &resp;

        int qret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(2000));
        if (qret == 0) {
            if (k_sem_take(&resp.sem, K_MSEC(45000)) != 0) {
                LOG_ERR("Timeout waiting for sd_worker unmount; skip force SD power-off");
            } else if (resp.res < 0) {
                LOG_ERR("sd_worker unmount failed: %d", resp.res);
            } else {
                unmount_completed = true;
            }
        } else {
            LOG_ERR("Failed to queue sd unmount request: %d", qret);
        }
    }

    /* Avoid forcing SD power-off while worker may still be writing/syncing,
     * which can trigger SPI transfer timeouts and filesystem corruption. */
    if (unmount_completed || !is_mounted) {
        if (sd_enabled) {
            sd_enable_power(false);
        }
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
    if (!buf || buf_size < MAX_FILENAME_LEN)
        return -EINVAL;
    strncpy(buf, current_filename, buf_size - 1);
    buf[buf_size - 1] = '\0';
    return 0;
}

void sd_notify_time_synced(uint32_t utc_time)
{
    pending_time_synced_utc = utc_time;
    atomic_set(&pending_time_synced, 1);

    sd_req_t req = {0};
    req.type = REQ_TIME_SYNCED;
    req.u.time_synced.utc_time = utc_time;
    /* Use priority queue if possible; otherwise worker will handle deferred flag. */
    int ret = k_msgq_put(&sd_prio_msgq, &req, K_NO_WAIT);
    if (ret == 0) {
        atomic_set(&pending_time_synced, 0);
    }
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
        req.u.create_file.resp = NULL; /* no response needed */
        int ret = k_msgq_put(&sd_prio_msgq, &req, K_NO_WAIT);
        if (ret) {
            atomic_set(&pending_flush_on_ble_connect, 1);
            LOG_WRN("Flush on BLE connect deferred (%d)", ret);
        }
    } else if (!connected && ble_connected) {
        LOG_INF("BLE disconnected");
        if (deferred_timesync_rename_pending) {
            sd_req_t req = {0};
            req.type = REQ_TIME_SYNCED;
            req.u.time_synced.utc_time = deferred_timesync_utc_time;
            int ret = k_msgq_put(&sd_prio_msgq, &req, K_NO_WAIT);
            if (ret == 0) {
                deferred_timesync_rename_pending = false;
                LOG_INF("Queued deferred TMP rename after BLE disconnect");
            } else {
                pending_time_synced_utc = deferred_timesync_utc_time;
                atomic_set(&pending_time_synced, 1);
                LOG_WRN("Deferred TMP rename pending (%d)", ret);
            }
        }
        if (current_file_deleted) {
            int cr = create_new_audio_file();
            if (cr < 0)
                LOG_ERR("create file on BLE disconnect failed: %d", cr);
            else
                current_file_deleted = false;
        }
    }
    ble_connected = connected;
}

uint32_t write_to_file(uint8_t *data, uint32_t length)
{
    static int64_t last_write_err_log_ms;
    static int64_t last_shutdown_drop_log_ms;

    /* Silently discard data while SD boot init is still running
     * (mount + lfs_fs_gc pre-warm + file open). No logging here to
     * avoid flooding — the worker thread logs when ready. */
    if (!atomic_get(&sd_boot_ready)) {
        static int64_t last_not_ready_log_ms;
        int64_t now = k_uptime_get();
        if (now - last_not_ready_log_ms > 5000) {
            LOG_WRN("write_to_file dropped: SD not ready (boot in progress)");
            last_not_ready_log_ms = now;
        }
        return 0;
    }

    if (sd_shutdown_in_progress) {
        int64_t now = k_uptime_get();
        if (now - last_shutdown_drop_log_ms > 1000) {
            LOG_WRN("write_to_file dropped: SD %s",
                    sd_shutdown_in_progress ? "shutdown" : "paused");
            last_shutdown_drop_log_ms = now;
        }
        return 0;
    }

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
    /* Fast path: non-blocking enqueue first. */
    int ret = k_msgq_put(&sd_msgq, &req, K_NO_WAIT);

    /* Backpressure: if queue is temporarily full, wait a very short time
     * for worker to drain instead of dropping immediately.
     * This reduces packet loss and CPU spin when SD path stalls briefly. */
    if (ret != 0) {
        k_timeout_t retry_wait = ble_connected ? K_MSEC(1) : K_MSEC(5);
        ret = k_msgq_put(&sd_msgq, &req, retry_wait);
    }

    if (ret) {
        write_drop_packets++;
        write_drop_bytes += length;
        int64_t now = k_uptime_get();
        if (now - last_write_err_log_ms > 2000) {
            LOG_WRN("Write queue full, dropping audio data (%d), dropped=%u pkts (%u bytes)",
                    ret,
                    write_drop_packets,
                    write_drop_bytes);
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
    req.u.read.length = amount;
    req.u.read.offset = offset;
    req.u.read.resp = &resp;

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
    if (resp.res) {
        LOG_ERR("read_audio_data failed: %d", resp.res);
        return -1;
    }
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
    if (!filename)
        return -EINVAL;

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
    if (resp.res) {
        LOG_ERR("clear_audio_directory failed: %d", resp.res);
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

    int ret = k_msgq_put(&sd_msgq, &req, K_MSEC(20));
    if (ret) {
        LOG_ERR("Failed to queue save_offset: %d", ret);
        return -1;
    }
    return 0;
}

int get_offset(char *filename, uint32_t *offset)
{
    if (!filename || !offset)
        return -EINVAL;
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

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(2000));
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
    if (resp.res) {
        LOG_ERR("create_new_audio_file failed: %d", resp.res);
        return -1;
    }

    if (ble_connected)
        ble_connect_time_ms = k_uptime_get();
    return 0;
}

int get_audio_file_stats(uint32_t *file_count, uint64_t *total_size)
{
    if (!file_count || !total_size)
        return -EINVAL;

    if (sd_shutdown_in_progress) {
        if (cached_stats_valid_until_ms > 0) {
            *file_count = cached_stats_file_count;
            *total_size = cached_stats_total_size;
            return 0;
        }
        return -ECANCELED;
    }

    static struct file_stats_resp resp;
    static volatile bool stats_in_flight;
    int64_t now = k_uptime_get();
    k_timeout_t wait_timeout = ble_connected ? K_MSEC(1000) : K_MSEC(30000);

    if (now < cached_stats_valid_until_ms) {
        *file_count = cached_stats_file_count;
        *total_size = cached_stats_total_size;
        return 0;
    }

    if (stats_in_flight) {
        if (k_sem_take(&resp.sem, K_NO_WAIT) == 0) {
            stats_in_flight = false;
        } else {
            LOG_WRN("get_audio_file_stats: previous request still in-flight");
            if (cached_stats_valid_until_ms > 0) {
                *file_count = cached_stats_file_count;
                *total_size = cached_stats_total_size;
                return 0;
            }
            return -EBUSY;
        }
    }
    stats_in_flight = true;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_GET_FILE_STATS;
    req.u.file_stats.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(2000));
    if (ret) {
        LOG_ERR("Failed to queue get_file_stats: %d", ret);
        stats_in_flight = false;
        if (cached_stats_valid_until_ms > 0) {
            *file_count = cached_stats_file_count;
            *total_size = cached_stats_total_size;
            return 0;
        }
        return -1;
    }

    if (k_sem_take(&resp.sem, wait_timeout) != 0) {
        LOG_ERR("Timeout waiting for get_file_stats");
        stats_in_flight = false;
        if (cached_stats_valid_until_ms > 0) {
            *file_count = cached_stats_file_count;
            *total_size = cached_stats_total_size;
            return 0;
        }
        return -ETIMEDOUT;
    }
    stats_in_flight = false;
    if (resp.res) {
        LOG_ERR("get_audio_file_stats failed: %d", resp.res);
        return -1;
    }

    cached_stats_file_count = resp.file_count;
    cached_stats_total_size = resp.total_size;
    cached_stats_valid_until_ms = k_uptime_get() + FILE_CACHE_TTL_MS;

    *file_count = resp.file_count;
    *total_size = resp.total_size;
    return 0;
}

int get_audio_file_list(char filenames[][MAX_FILENAME_LEN], int max_files, int *count)
{
    if (!filenames || !count || max_files <= 0)
        return -EINVAL;

    if (sd_shutdown_in_progress) {
        return -ECANCELED;
    }

    /* Fast path: during boot the worker is blocked in lfs_fs_gc(),
     * so it cannot service the priority queue.  Return the file list
     * that was cached during print_audio_files_at_boot() instead. */
    if (!atomic_get(&sd_boot_ready) && file_cache_valid) {
        int n = cached_file_list_count < max_files ? cached_file_list_count : max_files;
        for (int i = 0; i < n; i++) {
            strncpy(filenames[i], cached_file_names[i], MAX_FILENAME_LEN - 1);
            filenames[i][MAX_FILENAME_LEN - 1] = '\0';
        }
        *count = n;
        return 0;
    }

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
    req.u.file_list.sizes = NULL; /* no sizes requested */
    req.u.file_list.max_files = max_files;
    req.u.file_list.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(2000));
    if (ret) {
        LOG_ERR("Failed to queue get_file_list: %d", ret);
        list_in_flight = false;
        return ret;
    }

    if (k_sem_take(&resp.sem, K_MSEC(5000)) != 0) {
        LOG_ERR("Timeout waiting for get_file_list");
        list_in_flight = false;
        return -ETIMEDOUT;
    }
    list_in_flight = false;
    if (resp.res) {
        LOG_ERR("get_audio_file_list failed: %d", resp.res);
        return resp.res;
    }

    *count = resp.count;
    return 0;
}

int get_audio_file_list_with_sizes(char filenames[][MAX_FILENAME_LEN], uint32_t *sizes, int max_files, int *count)
{
    if (!filenames || !count || max_files <= 0)
        return -EINVAL;

    if (sd_shutdown_in_progress) {
        return -ECANCELED;
    }

    /* Fast path: during boot the worker is blocked in lfs_fs_gc(),
     * so it cannot service the priority queue.  Return the file list
     * that was cached during print_audio_files_at_boot() instead. */
    if (!atomic_get(&sd_boot_ready) && file_cache_valid) {
        int n = cached_file_list_count < max_files ? cached_file_list_count : max_files;
        for (int i = 0; i < n; i++) {
            strncpy(filenames[i], cached_file_names[i], MAX_FILENAME_LEN - 1);
            filenames[i][MAX_FILENAME_LEN - 1] = '\0';
            if (sizes) {
                sizes[i] = cached_file_sizes[i];
            }
        }
        *count = n;
        return 0;
    }

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
    req.u.file_list.sizes = sizes;
    req.u.file_list.max_files = max_files;
    req.u.file_list.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret) {
        LOG_ERR("Failed to queue get_file_list: %d", ret);
        list_sizes_in_flight = false;
        return ret;
    }

    if (k_sem_take(&resp.sem, K_MSEC(5000)) != 0) {
        LOG_ERR("Timeout waiting for get_file_list");
        list_sizes_in_flight = false;
        return -ETIMEDOUT;
    }
    list_sizes_in_flight = false;
    if (resp.res) {
        LOG_ERR("get_audio_file_list_with_sizes failed: %d", resp.res);
        return resp.res;
    }

    *count = resp.count;
    return 0;
}
