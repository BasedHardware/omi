#include "lib/core/sd_card.h"
#include "lib/core/transport.h"
#include <ff.h>
#include <zephyr/fs/fs.h>
#include <string.h>
#include <stdio.h>
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
#define SD_REQ_QUEUE_MSGS  100      // Number of messages in the SD request queue
#define SD_FSYNC_THRESHOLD 20000    // Threshold in bytes to trigger fsync
#define WRITE_BATCH_COUNT 10        // Number of writes to batch before writing to SD card
#define ERROR_THRESHOLD 5           // Maximum allowed write errors before taking action
#define CHUNK_DURATION_SECONDS 300  // 5 minutes per chunk file
#define MAX_FILENAME_LEN 64         // Maximum filename length

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
#define FILE_DATA_PATH "/SD:/audio/a01.txt"
#define FILE_INFO_PATH "/SD:/info.txt"

static struct fs_file_t fil_data;
static struct fs_file_t fil_info;

static bool is_mounted = false;
static bool sd_enabled = false;
static uint32_t current_file_size = 0;
static size_t bytes_since_sync = 0;

// Time-based chunking state
static bool is_chunking_mode = false;
static int64_t current_chunk_start_time = 0;  // Uptime in milliseconds when current chunk started
static char current_chunk_file_path[MAX_FILENAME_LEN] = {0};
static uint32_t current_chunk_file_size = 0;
static uint32_t chunk_file_counter = 0;  // Persistent counter for unique chunk filenames

// Get the device pointer for the SDHC SPI slot from the device tree
static const struct device *const sd_dev = DEVICE_DT_GET(DT_NODELABEL(sdhc0));
static const struct gpio_dt_spec sd_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

K_MSGQ_DEFINE(sd_msgq, sizeof(sd_req_t), SD_REQ_QUEUE_MSGS, 4);

void sd_worker_thread(void);

static int sd_enable_power(bool enable)
{
    int ret;
    gpio_pin_configure_dt(&sd_en, GPIO_OUTPUT);
    if (enable) {
        ret = gpio_pin_set_dt(&sd_en, 1);
        pm_device_action_run(sd_dev, PM_DEVICE_ACTION_RESUME);
        sd_enabled = true;
    } else {
        ret = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_SUSPEND);
        // gpio_pin_set_dt(&sd_en, 0);
        sd_enabled = false;
    }
    return ret;
}

static int sd_unmount()
{
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

uint32_t get_file_size()
{
    return current_file_size;
}

int read_audio_data(uint8_t *buf, int amount, int offset)
{
    struct read_resp resp;
    k_sem_init(&resp.sem, 0, 1);

    sd_req_t req = {0};
    req.type = REQ_READ_DATA;
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

    save_offset(0);

    return 0;
}

int save_offset(uint32_t offset)
{
    sd_req_t req = {0};
    req.type = REQ_SAVE_OFFSET;
    req.u.info.offset_value = offset;

    int ret = k_msgq_put(&sd_msgq, &req, K_MSEC(100));
    if (ret) {
        LOG_ERR("Failed to queue save_offset request: %d", ret);
        return -1;
    }
    return 0;
}

uint32_t get_offset(void)
{
    struct read_resp resp;
    k_sem_init(&resp.sem, 0, 1);

    uint32_t offset;
    sd_req_t req = {0};
    req.type = REQ_READ_OFFSET;
    req.u.offset.resp = &resp;
    req.u.offset.out_offset = &offset;

    int ret = k_msgq_put(&sd_msgq, &req, K_MSEC(100));
    if (ret != 0) {
        LOG_ERR("Failed to queue get_offset request: %d", ret);
        return 0;
    }

    // wait for sd_worker_thread to finish processing
    if (k_sem_take(&resp.sem, K_MSEC(5000)) != 0) {
        LOG_ERR("Timeout waiting for get_offset response");
        return 0;
    }

    if (resp.res) {
        LOG_ERR("Failed to read offset from info file: %d", resp.res);
        return 0;
    }
    return offset;
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

/**
 * @brief Generate a unique filename for chunked audio files
 * Format: audio_<counter>_<uptime>.bin where counter is persistent and uptime is for uniqueness
 * Uses persistent counter to avoid collisions after reboot
 */
static void generate_chunk_filename(char *filename, size_t filename_size, uint32_t counter, int64_t uptime_sec)
{
    snprintf(filename, filename_size, "/SD:/audio/audio_%u_%lld.bin", counter, (long long)uptime_sec);
}

/**
 * @brief Check if we need to create a new chunk file (every 5 minutes)
 * Returns true if a new chunk should be created
 */
static bool should_create_new_chunk(void)
{
    if (!is_chunking_mode) {
        return false;
    }

    int64_t current_uptime_ms = k_uptime_get();
    int64_t elapsed_ms = current_uptime_ms - current_chunk_start_time;
    int64_t elapsed_sec = elapsed_ms / 1000;

    return (elapsed_sec >= CHUNK_DURATION_SECONDS);
}

/**
 * @brief Load chunk file counter from info file
 * Info file structure: [offset: 4 bytes][chunk_counter: 4 bytes]
 */
static uint32_t load_chunk_counter(void)
{
    struct fs_dirent info_stat;
    if (fs_stat(FILE_INFO_PATH, &info_stat) < 0 || info_stat.size < 8) {
        return 0;  // File doesn't exist or too small, start from 0
    }

    int seek_res = fs_seek(&fil_info, 4, FS_SEEK_SET);  // Skip offset, read counter
    if (seek_res < 0) {
        return 0;
    }

    uint32_t counter = 0;
    ssize_t rbytes = fs_read(&fil_info, &counter, sizeof(counter));
    if (rbytes != sizeof(counter)) {
        return 0;
    }

    return counter;
}

/**
 * @brief Save chunk file counter to info file
 * Info file structure: [offset: 4 bytes][chunk_counter: 4 bytes]
 */
static void save_chunk_counter(uint32_t counter)
{
    int seek_res = fs_seek(&fil_info, 4, FS_SEEK_SET);  // Skip offset, write counter
    if (seek_res < 0) {
        LOG_ERR("[SD_WORK] Failed to seek to counter position in info file");
        return;
    }

    ssize_t bw = fs_write(&fil_info, &counter, sizeof(counter));
    if (bw != sizeof(counter)) {
        LOG_ERR("[SD_WORK] Failed to write chunk counter to info file: %d", (int)bw);
    } else {
        fs_sync(&fil_info);
    }
}

/**
 * @brief Create a new chunk file with unique filename
 * Uses persistent counter + uptime for uniqueness to avoid collisions after reboot
 */
static int create_new_chunk_file(void)
{
    // Close current file if open
    if (strlen(current_chunk_file_path) > 0) {
        fs_close(&fil_data);
        fs_file_t_init(&fil_data);
    }

    // Increment and save persistent counter
    chunk_file_counter++;
    save_chunk_counter(chunk_file_counter);

    // Get current uptime for additional uniqueness (helps distinguish files created in same session)
    int64_t current_uptime_ms = k_uptime_get();
    int64_t current_uptime_sec = current_uptime_ms / 1000;
    
    // Generate filename with persistent counter + uptime for uniqueness
    generate_chunk_filename(current_chunk_file_path, sizeof(current_chunk_file_path), 
                           chunk_file_counter, current_uptime_sec);

    // Open new file
    int res = fs_open(&fil_data, current_chunk_file_path, FS_O_CREATE | FS_O_RDWR | FS_O_TRUNC);
    if (res < 0) {
        LOG_ERR("[SD_WORK] Failed to create new chunk file %s: %d\n", current_chunk_file_path, res);
        current_chunk_file_path[0] = '\0';
        return res;
    }

    current_chunk_start_time = current_uptime_ms;
    current_chunk_file_size = 0;
    current_file_size = 0;
    bytes_since_sync = 0;

    LOG_INF("[SD_WORK] Created new chunk file: %s (counter: %u)\n", current_chunk_file_path, chunk_file_counter);
    return 0;
}

/**
 * @brief Flush any pending batch data to current file
 */
static void flush_pending_batch(void)
{
    if (write_batch_offset > 0 && write_batch_counter > 0) {
        LOG_INF("[SD_WORK] Flushing pending batch data (%u bytes) before mode switch", 
                (unsigned)write_batch_offset);
        int res = fs_seek(&fil_data, 0, FS_SEEK_END);
        if (res < 0) {
            LOG_ERR("[SD_WORK] seek end before flush failed: %d\n", res);
        } else {
            ssize_t bw = fs_write(&fil_data, write_batch_buffer, write_batch_offset);
            if (bw > 0) {
                bytes_since_sync += bw;
                current_file_size += bw;
                if (is_chunking_mode) {
                    current_chunk_file_size += bw;
                }
                // Sync immediately when switching modes
                res = fs_sync(&fil_data);
                if (res < 0) {
                    LOG_ERR("[SD_WORK] fs_sync after flush failed: %d\n", res);
                }
            }
            write_batch_offset = 0;
            write_batch_counter = 0;
            bytes_since_sync = 0;
        }
    }
}

/**
 * @brief Enable or disable chunking mode based on connection status
 * Flushes pending data immediately when switching modes
 */
static void update_chunking_mode(void)
{
    struct bt_conn *conn = get_current_connection();
    bool should_chunk = (conn == NULL);

    if (should_chunk && !is_chunking_mode) {
        // Switching to chunking mode - flush any pending data first
        LOG_INF("[SD_WORK] Device disconnected, enabling time-based chunking mode");
        flush_pending_batch();
        is_chunking_mode = true;
        // Create first chunk file immediately
        create_new_chunk_file();
    } else if (!should_chunk && is_chunking_mode) {
        // Switching back to single file mode - flush any pending data first
        LOG_INF("[SD_WORK] Device connected, switching back to single file mode");
        flush_pending_batch();
        
        // Close current chunk file and switch back to default file
        if (strlen(current_chunk_file_path) > 0) {
            fs_close(&fil_data);
            fs_file_t_init(&fil_data);
            current_chunk_file_path[0] = '\0';
        }
        
        // Reopen default file - only switch out of chunking mode if successful
        int res = fs_open(&fil_data, FILE_DATA_PATH, FS_O_CREATE | FS_O_RDWR);
        if (res < 0) {
            LOG_ERR("[SD_WORK] Failed to reopen default file: %d. Staying in chunking mode to prevent inconsistent state.\n", res);
            // Don't switch out of chunking mode if we can't open the default file
            // This prevents leaving the system in a broken state
            return;
        }
        
        // Successfully opened default file, now switch out of chunking mode
        is_chunking_mode = false;
        fs_seek(&fil_data, 0, FS_SEEK_END);
        
        struct fs_dirent data_stat;
        if (fs_stat(FILE_DATA_PATH, &data_stat) == 0) {
            current_file_size = data_stat.size;
        } else {
            // Reset file size if stat fails to prevent inconsistent state
            current_file_size = 0;
        }
    }
}

/**
 * @brief Public function to force immediate chunking mode check
 * Can be called from transport layer on disconnection
 */
void sd_check_chunking_mode(void)
{
    sd_req_t req = {0};
    req.type = REQ_CHECK_CHUNKING_MODE;
    
    int ret = k_msgq_put(&sd_msgq, &req, K_MSEC(100));
    if (ret) {
        LOG_ERR("Failed to queue chunking mode check request: %d", ret);
    }
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
        LOG_ERR("[SD_WORK] mount failed: %d\n", res);
        return;
    }

    struct fs_dirent dirent;
    int stat_res = fs_stat(FILE_DATA_DIR, &dirent);
    if (stat_res < 0) {
        int mk_res = fs_mkdir(FILE_DATA_DIR);
        if (mk_res < 0) {
            LOG_ERR("[SD_WORK] mkdir %s failed: %d\n", FILE_DATA_DIR, mk_res);
        }
    }

    /* Initialize chunking state */
    is_chunking_mode = false;
    current_chunk_start_time = 0;
    current_chunk_file_path[0] = '\0';
    current_chunk_file_size = 0;

    /* Open data file (append) */
    fs_file_t_init(&fil_data);
    res = fs_open(&fil_data, FILE_DATA_PATH, FS_O_CREATE | FS_O_RDWR);
    if (res < 0) {
        LOG_ERR("[SD_WORK] open data failed: %d\n", res);
        return;
    } else {
        /* move to end for append writes by default */
        res = fs_seek(&fil_data, 0, FS_SEEK_END);
    }

    struct fs_dirent data_stat;
    int stat_res_data = fs_stat(FILE_DATA_PATH, &data_stat);
    if (stat_res_data == 0) {
        current_file_size = data_stat.size;
    } else {
        current_file_size = 0;
    }

    /* Open info file (read/write, create if not exists) */
    /* Info file structure: [offset: 4 bytes][chunk_counter: 4 bytes] */
    struct fs_dirent info_stat;
    int info_exists = fs_stat(FILE_INFO_PATH, &info_stat);
    fs_file_t_init(&fil_info);
    res = fs_open(&fil_info, FILE_INFO_PATH, FS_O_CREATE | FS_O_RDWR);
    if (res < 0) {
        LOG_ERR("[SD_WORK] open info failed: %d\n", res);
        return;
    } else {
        bool need_init = false;
        if (info_exists < 0) {
            need_init = true;
        } else if (info_stat.size < 8) {  // Need at least 8 bytes: offset (4) + counter (4)
            need_init = true;
        }
        if (need_init) {
            // Initialize with zero offset and zero counter
            uint32_t zero_offset = 0;
            uint32_t zero_counter = 0;
            ssize_t bw = fs_write(&fil_info, &zero_offset, sizeof(zero_offset));
            if (bw != sizeof(zero_offset)) {
                LOG_ERR("[SD_WORK] init info.txt failed to write offset: %d\n", (int)bw);
            } else {
                bw = fs_write(&fil_info, &zero_counter, sizeof(zero_counter));
                if (bw != sizeof(zero_counter)) {
                    LOG_ERR("[SD_WORK] init info.txt failed to write counter: %d\n", (int)bw);
                } else {
                    fs_sync(&fil_info);
                }
            }
        }

        // Load persistent chunk counter
        chunk_file_counter = load_chunk_counter();
        LOG_INF("[SD_WORK] Loaded chunk file counter: %u", chunk_file_counter);

        fs_seek(&fil_data, 0, FS_SEEK_END);
    }

    while (1) {
        /* Wait for a request with timeout to allow periodic checks */
        if (k_msgq_get(&sd_msgq, &req, K_MSEC(500)) == 0) {
            switch (req.type) {
            case REQ_WRITE_DATA:
                // Check if we need to create a new chunk file
                // Note: update_chunking_mode() is called via REQ_CHECK_CHUNKING_MODE and periodic checks,
                // not on every write to avoid performance overhead
                if (should_create_new_chunk()) {
                    LOG_INF("[SD_WORK] Chunk duration reached, creating new chunk file");
                    create_new_chunk_file();
                }

                LOG_DBG("[SD_WORK] Buffering %u bytes to batch write\n", (unsigned)req.u.write.len);

                memcpy(write_batch_buffer + write_batch_offset, req.u.write.buf, req.u.write.len);
                write_batch_offset += req.u.write.len;
                write_batch_counter++;

                if (write_batch_counter >= WRITE_BATCH_COUNT) {
                    LOG_INF("[SD_WORK] WRITE_BATCH_COUNT reached. Flushing batch write.");
                    res = fs_seek(&fil_data, 0, FS_SEEK_END);
                    if (res < 0) {
                        LOG_ERR("[SD_WORK] seek end before write failed: %d\n", res);
                    }
                    bw = fs_write(&fil_data, write_batch_buffer, write_batch_offset);
                    if (bw < 0 || (size_t)bw != write_batch_offset) {
                        writing_error_counter++;

                        LOG_ERR("[SD_WORK] batch write error %d bw=%d wanted=%u\n", (int)bw, (int)bw, (unsigned)write_batch_offset);
                        if (bw > 0) {
                            LOG_INF("Attempting to truncate to correct packet position");
                            uint32_t truncate_offset = current_file_size + bw - bw % MAX_WRITE_SIZE;
                            int ret = fs_truncate(&fil_data, truncate_offset);
                            if (ret < 0) {
                                LOG_ERR("Failed to truncate to next packet position: %d", ret);
                                break;
                            }
                            LOG_INF("Shifted file pointer to correct packet position: %u", truncate_offset);
                            current_file_size += bw - bw % MAX_WRITE_SIZE;
                        }

                        if (writing_error_counter >= ERROR_THRESHOLD) {
                            LOG_ERR("[SD_WORK] Too many write errors (%d). Stopping SD worker.\n", writing_error_counter);
                            fs_close(&fil_data);
                            fs_file_t_init(&fil_data);
                            LOG_INF("[SD_WORK] Re-opening data file after too many errors.\n");
                            // Use appropriate file based on chunking mode
                            const char *file_to_reopen = is_chunking_mode && strlen(current_chunk_file_path) > 0 
                                ? current_chunk_file_path 
                                : FILE_DATA_PATH;
                            int reopen_res = fs_open(&fil_data, file_to_reopen, FS_O_CREATE | FS_O_RDWR);
                            if (reopen_res == 0) {
                                writing_error_counter = 0;
                                fs_seek(&fil_data, 0, FS_SEEK_END);
                            } else {
                                LOG_ERR("[SD_WORK] open new data file failed: %d. Terminating operation", reopen_res);
                            }
                        }

                        write_batch_offset = 0;
                        write_batch_counter = 0;
                        break;
                    }

                    bytes_since_sync += bw > 0 ? bw : 0;
                    current_file_size += bw > 0 ? bw : 0;
                    if (is_chunking_mode) {
                        current_chunk_file_size += bw > 0 ? bw : 0;
                    }
                    write_batch_offset = 0;
                    write_batch_counter = 0;
                }

                if (bytes_since_sync >= SD_FSYNC_THRESHOLD) {
                    LOG_INF("[SD_WORK] fs_sync triggered after %u bytes\n", (unsigned)bytes_since_sync);
                    res = fs_sync(&fil_data);
                    if (res < 0) {
                        LOG_ERR("[SD_WORK] fs_sync data failed: %d\n", res);
                    }
                    bytes_since_sync = 0;
                }

                break;

            case REQ_READ_DATA:
                LOG_DBG("[SD_WORK] Reading %u bytes from data file at offset %u\n",
                        (unsigned)req.u.read.length, (unsigned)req.u.read.offset);
                if (&fil_data == NULL) {
                    LOG_ERR("[SD_WORK] data file not open (read)\n");
                    if (req.u.read.resp) {
                        req.u.read.resp->res = -1;
                        req.u.read.resp->read_bytes = 0;
                        k_sem_give(&req.u.read.resp->sem);
                    }
                    break;
                }

                res = fs_seek(&fil_data, req.u.read.offset, FS_SEEK_SET);
                if (res < 0) {
                    LOG_ERR("[SD_WORK] lseek failed: %d\n", res);
                    if (req.u.read.resp) {
                        req.u.read.resp->res = res;
                        req.u.read.resp->read_bytes = 0;
                        k_sem_give(&req.u.read.resp->sem);
                    }
                    break;
                }
                br = fs_read(&fil_data, req.u.read.out_buf, req.u.read.length);
                if (req.u.read.resp) {
                    req.u.read.resp->res = (br < 0) ? br : 0;
                    req.u.read.resp->read_bytes = (br < 0) ? 0 : br;
                    k_sem_give(&req.u.read.resp->sem);
                }
                break;

            case REQ_SAVE_OFFSET:
                LOG_DBG("[SD_WORK] Saving offset %u to info file\n", (unsigned)req.u.info.offset_value);
                /* Write offset to info.txt (first 4 bytes), preserving chunk counter (next 4 bytes) */
                if (&fil_info == NULL) {
                    LOG_ERR("[SD_WORK] info file not open\n");
                    break;
                }
                res = fs_seek(&fil_info, 0, FS_SEEK_SET);
                if (res == 0) {
                    bw = fs_write(&fil_info, &req.u.info.offset_value, sizeof(req.u.info.offset_value));
                    if (bw < 0 || bw != sizeof(req.u.info.offset_value)) {
                        LOG_ERR("[SD_WORK] info write err %d\n", (int)bw);
                    } else {
                        res = fs_sync(&fil_info);
                        if (res < 0) {
                            LOG_ERR("[SD_WORK] fs_sync of info file failed: %d", res);
                        }
                    }
                }
                break;

            case REQ_CLEAR_AUDIO_DIR:
                LOG_DBG("[SD_WORK] Clearing audio directory (delete files only)");
                // Close fil_data before clearing directory
                fs_close(&fil_data);
                int unlink_res = fs_unlink(FILE_DATA_PATH);
                if (unlink_res != 0 && unlink_res != -2) {
                    LOG_ERR("[SD_WORK] Cannot unlink data file: %s, err: %d", FILE_DATA_PATH, unlink_res);
                }
                fs_file_t_init(&fil_data);
                int reopen_res = fs_open(&fil_data, FILE_DATA_PATH, FS_O_CREATE | FS_O_RDWR | FS_O_TRUNC);
                if (reopen_res == 0) {
                    fs_seek(&fil_data, 0, FS_SEEK_SET);
                } else {
                    LOG_ERR("[SD_WORK] open new data file failed: %d. Terminating operation", reopen_res);
                    return;
                }
                current_file_size = 0;
                // Return result to resp if available
                if (req.u.clear_dir.resp) {
                    req.u.clear_dir.resp->res = 0;
                    k_sem_give(&req.u.clear_dir.resp->sem);
                }
                break;

            case REQ_READ_OFFSET:
                LOG_DBG("[SD_WORK] Reading offset from info file\n");
                /* read offset from file info.txt (first 4 bytes) */
                /* Info file structure: [offset: 4 bytes][chunk_counter: 4 bytes] */
                if (&fil_info == NULL) {
                    LOG_ERR("[SD_WORK] info file not open (read offset)\n");
                    if (req.u.offset.resp) {
                        req.u.offset.resp->res = -1;
                        k_sem_give(&req.u.offset.resp->sem);
                    }
                    break;
                }

                int seek_res = fs_seek(&fil_info, 0, FS_SEEK_SET);
                if (seek_res < 0) {
                    LOG_ERR("[SD_WORK] seek info failed: %d\n", seek_res);
                    if (req.u.offset.resp) {
                        req.u.offset.resp->res = seek_res;
                        k_sem_give(&req.u.offset.resp->sem);
                    }
                    break;
                }
                uint32_t offset_val = 0;
                ssize_t rbytes = fs_read(&fil_info, &offset_val, sizeof(offset_val));
                if (rbytes != sizeof(offset_val)) {
                    LOG_ERR("[SD_WORK] read offset failed: %d\n", (int)rbytes);
                    if (req.u.offset.resp) {
                        req.u.offset.resp->res = (int)rbytes;
                        k_sem_give(&req.u.offset.resp->sem);
                    }
                    break;
                }
                if (req.u.offset.out_offset) {
                    *req.u.offset.out_offset = offset_val;
                }
                if (req.u.offset.resp) {
                    req.u.offset.resp->res = 0;
                    k_sem_give(&req.u.offset.resp->sem);
                }
                break;
            case REQ_CHECK_CHUNKING_MODE:
                // Immediate check and mode switch
                LOG_DBG("[SD_WORK] Forced chunking mode check");
                update_chunking_mode();
                break;

            default:
                LOG_ERR("[SD_WORK] unknown req type\n");
            }
        } else {
            // Timeout - no request pending, check connection status periodically
            // This ensures immediate mode switch even when no writes are happening
            static int64_t last_check_time = 0;
            int64_t current_time = k_uptime_get();
            // Check every 500ms when idle
            if (current_time - last_check_time >= 500) {
                update_chunking_mode();
                last_check_time = current_time;
            }
        }
    }
}