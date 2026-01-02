#include "sdcard.h"

#include <ff.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/fs/fs.h>
#include <zephyr/fs/fs_sys.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/check.h>
#include <zephyr/pm/device.h>

LOG_MODULE_REGISTER(sdcard, CONFIG_LOG_DEFAULT_LEVEL);

#define DISK_DRIVE_NAME "SD"
#define DISK_MOUNT_PT "/SD:"
#define SD_REQ_QUEUE_MSGS  100
#define SD_FSYNC_THRESHOLD 20000
#define WRITE_BATCH_COUNT 10
#define ERROR_THRESHOLD 5

// Batch write buffer
static uint8_t write_batch_buffer[WRITE_BATCH_COUNT * MAX_WRITE_SIZE];
static size_t write_batch_offset = 0;
static int write_batch_counter = 0;
static uint8_t writing_error_counter = 0;

static FATFS fat_fs;

static struct fs_mount_t mount_point = {
    .type = FS_FATFS,
    .fs_data = &fat_fs,
};

#define FILE_DATA_DIR "/SD:/audio"
#define FILE_DATA_PATH "/SD:/audio/a01.txt"
#define FILE_INFO_PATH "/SD:/info.txt"

static struct fs_file_t fil_data;
static struct fs_file_t fil_info;

static bool is_mounted = false;
static bool sd_enabled = false;
static uint32_t current_file_size = 0;
static uint32_t current_file_offset = 0;
static size_t bytes_since_sync = 0;

// DevKit-specific GPIO for SD card enable
struct gpio_dt_spec sd_en_gpio_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio0)),
                                      .pin = 19,
                                      .dt_flags = 0};

// Message queue for SD worker
K_MSGQ_DEFINE(sd_msgq, sizeof(sd_req_t), SD_REQ_QUEUE_MSGS, 4);

// Worker thread
#define SD_WORKER_STACK_SIZE 4096
#define SD_WORKER_PRIORITY 7
K_THREAD_STACK_DEFINE(sd_worker_stack, SD_WORKER_STACK_SIZE);
static struct k_thread sd_worker_thread_data;
static k_tid_t sd_worker_tid = NULL;

void sd_worker_thread(void);

// Backward compatibility - keep these for code that still references them
uint8_t file_count = 1;
uint32_t file_num_array[2];

#define MAX_PATH_LENGTH 32
static char current_full_path[MAX_PATH_LENGTH];
static char read_buffer_path[MAX_PATH_LENGTH];
static char write_buffer_path[MAX_PATH_LENGTH];
static const char *disk_mount_pt = "/SD:/";

// Internal mount function (called by worker thread)
static int internal_mount_sd_card(void)
{
    // Initialize the sd card enable pin
    if (gpio_is_ready_dt(&sd_en_gpio_pin)) {
        LOG_INF("SD Enable Pin ready");
    } else {
        LOG_ERR("Error setting up SD Enable Pin");
        return -1;
    }

    if (gpio_pin_configure_dt(&sd_en_gpio_pin, GPIO_OUTPUT_ACTIVE) < 0) {
        LOG_ERR("Error setting up SD Pin");
        return -1;
    }
    sd_enabled = true;

    // Initialize the sd card
    const char *disk_pdrv = "SD";
    int err = disk_access_init(disk_pdrv);
    LOG_INF("disk_access_init: %d", err);
    if (err) {
        k_msleep(1000);
        err = disk_access_init(disk_pdrv);
        if (err) {
            LOG_ERR("disk_access_init failed");
            return -1;
        }
    }

    mount_point.mnt_point = DISK_MOUNT_PT;
    int res = fs_mount(&mount_point);
    if (res == FR_OK) {
        LOG_INF("SD card mounted successfully");
        is_mounted = true;
    } else {
        LOG_ERR("f_mount failed: %d", res);
        return -1;
    }

    return 0;
}

static int internal_unmount(void)
{
    // Ensure files are closed before unmounting
    fs_close(&fil_data);
    fs_close(&fil_info);
    
    int ret = fs_unmount(&mount_point);
    if (ret) {
        LOG_INF("Disk unmount error: %d", ret);
        return ret;
    }

    LOG_INF("Disk unmounted.");
    is_mounted = false;
    return 0;
}

/* SD worker thread */
void sd_worker_thread(void)
{
    sd_req_t req;
    int res;
    ssize_t bw = 0, br = 0;

    /* Mount the SD card */
    res = internal_mount_sd_card();
    if (res != 0) {
        LOG_ERR("[SD_WORK] mount failed: %d", res);
        return;
    }

    /* Create audio directory if needed */
    struct fs_dirent dirent;
    int stat_res = fs_stat(FILE_DATA_DIR, &dirent);
    if (stat_res < 0) {
        int mk_res = fs_mkdir(FILE_DATA_DIR);
        if (mk_res < 0 && mk_res != -EEXIST) {
            LOG_ERR("[SD_WORK] mkdir %s failed: %d", FILE_DATA_DIR, mk_res);
        }
    }

    /* Open data file */
    fs_file_t_init(&fil_data);
    res = fs_open(&fil_data, FILE_DATA_PATH, FS_O_CREATE | FS_O_RDWR);
    if (res < 0) {
        LOG_ERR("[SD_WORK] open data failed: %d", res);
        return;
    } else {
        /* Move to end for append writes by default */
        res = fs_seek(&fil_data, 0, FS_SEEK_END);
    }

    /* Get initial file size */
    struct fs_dirent data_stat;
    int stat_res_data = fs_stat(FILE_DATA_PATH, &data_stat);
    if (stat_res_data == 0) {
        current_file_size = data_stat.size;
    } else {
        current_file_size = 0;
    }
    
    /* Update backward-compat array */
    file_num_array[0] = current_file_size;

    /* Open info file */
    struct fs_dirent info_stat;
    int info_exists = fs_stat(FILE_INFO_PATH, &info_stat);
    fs_file_t_init(&fil_info);
    res = fs_open(&fil_info, FILE_INFO_PATH, FS_O_CREATE | FS_O_RDWR);
    if (res < 0) {
        LOG_ERR("[SD_WORK] open info failed: %d", res);
        return;
    } else {
        bool need_init_offset = false;
        if (info_exists < 0) {
            need_init_offset = true;
        } else if (info_stat.size < sizeof(uint32_t)) {
            need_init_offset = true;
        }
        
        if (need_init_offset) {
            current_file_offset = 0;
            uint32_t zero_offset = 0;
            ssize_t written = fs_write(&fil_info, &zero_offset, sizeof(zero_offset));
            if (written != sizeof(zero_offset)) {
                LOG_ERR("[SD_WORK] init info.txt failed to write offset 0: %d", (int)written);
            } else {
                fs_sync(&fil_info);
            }
        } else {
            /* Read existing offset from info.txt */
            fs_seek(&fil_info, 0, FS_SEEK_SET);
            ssize_t rbytes = fs_read(&fil_info, &current_file_offset, sizeof(current_file_offset));
            if (rbytes != sizeof(current_file_offset)) {
                LOG_ERR("[SD_WORK] Failed to read offset at boot: %d", (int)rbytes);
                current_file_offset = 0;
            } else {
                LOG_INF("[SD_WORK] Loaded offset from info.txt: %u", current_file_offset);
            }
        }

        fs_seek(&fil_data, 0, FS_SEEK_END);
    }
    
    /* Update backward-compat array */
    file_num_array[1] = current_file_offset;

    LOG_INF("[SD_WORK] Worker thread started. File size: %u, Offset: %u", 
            current_file_size, current_file_offset);

    while (1) {
        /* Wait for a request */
        if (k_msgq_get(&sd_msgq, &req, K_FOREVER) == 0) {
            switch (req.type) {
            case REQ_WRITE_DATA:
                LOG_DBG("[SD_WORK] Buffering %u bytes to batch write", (unsigned)req.u.write.len);

                memcpy(write_batch_buffer + write_batch_offset, req.u.write.buf, req.u.write.len);
                write_batch_offset += req.u.write.len;
                write_batch_counter++;

                if (write_batch_counter >= WRITE_BATCH_COUNT) {
                    LOG_INF("[SD_WORK] WRITE_BATCH_COUNT reached. Flushing batch write.");
                    res = fs_seek(&fil_data, 0, FS_SEEK_END);
                    if (res < 0) {
                        LOG_ERR("[SD_WORK] seek end before write failed: %d", res);
                    }
                    bw = fs_write(&fil_data, write_batch_buffer, write_batch_offset);
                    if (bw < 0 || (size_t)bw != write_batch_offset) {
                        writing_error_counter++;
                        LOG_ERR("[SD_WORK] batch write error bw=%d wanted=%u", 
                                (int)bw, (unsigned)write_batch_offset);
                        
                        if (bw > 0) {
                            LOG_INF("Attempting to truncate to correct packet position");
                            uint32_t truncate_offset = current_file_size + bw - bw % MAX_WRITE_SIZE;
                            int ret = fs_truncate(&fil_data, truncate_offset);
                            if (ret < 0) {
                                LOG_ERR("Failed to truncate: %d", ret);
                            } else {
                                current_file_size += bw - bw % MAX_WRITE_SIZE;
                            }
                        }

                        if (writing_error_counter >= ERROR_THRESHOLD) {
                            LOG_ERR("[SD_WORK] Too many write errors (%d). Re-opening file.", 
                                    writing_error_counter);
                            fs_close(&fil_data);
                            fs_file_t_init(&fil_data);
                            int reopen_res = fs_open(&fil_data, FILE_DATA_PATH, FS_O_CREATE | FS_O_RDWR);
                            if (reopen_res == 0) {
                                writing_error_counter = 0;
                                fs_seek(&fil_data, 0, FS_SEEK_END);
                            } else {
                                LOG_ERR("[SD_WORK] Re-open failed: %d", reopen_res);
                            }
                        }

                        write_batch_offset = 0;
                        write_batch_counter = 0;
                        break;
                    }

                    bytes_since_sync += bw > 0 ? bw : 0;
                    current_file_size += bw > 0 ? bw : 0;
                    file_num_array[0] = current_file_size;
                    write_batch_offset = 0;
                    write_batch_counter = 0;
                }

                if (bytes_since_sync >= SD_FSYNC_THRESHOLD) {
                    LOG_INF("[SD_WORK] fs_sync triggered after %u bytes", (unsigned)bytes_since_sync);
                    res = fs_sync(&fil_data);
                    if (res < 0) {
                        LOG_ERR("[SD_WORK] fs_sync data failed: %d", res);
                    }
                    bytes_since_sync = 0;
                }
                break;

            case REQ_READ_DATA:
                LOG_DBG("[SD_WORK] Reading %u bytes at offset %u",
                        (unsigned)req.u.read.length, (unsigned)req.u.read.offset);

                res = fs_seek(&fil_data, req.u.read.offset, FS_SEEK_SET);
                if (res < 0) {
                    LOG_ERR("[SD_WORK] seek failed: %d", res);
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
                LOG_DBG("[SD_WORK] Saving offset %u", (unsigned)req.u.info.offset_value);
                res = fs_seek(&fil_info, 0, FS_SEEK_SET);
                if (res == 0) {
                    bw = fs_write(&fil_info, &req.u.info.offset_value, sizeof(req.u.info.offset_value));
                    if (bw < 0 || bw != sizeof(req.u.info.offset_value)) {
                        LOG_ERR("[SD_WORK] info write err %d", (int)bw);
                    } else {
                        res = fs_sync(&fil_info);
                        if (res < 0) {
                            LOG_ERR("[SD_WORK] fs_sync info failed: %d", res);
                        } else {
                            current_file_offset = req.u.info.offset_value;
                            file_num_array[1] = current_file_offset;
                        }
                    }
                }
                break;

            case REQ_READ_OFFSET:
                LOG_DBG("[SD_WORK] Reading offset");
                if (req.u.offset.out_offset) {
                    *req.u.offset.out_offset = current_file_offset;
                }
                if (req.u.offset.resp) {
                    req.u.offset.resp->res = 0;
                    k_sem_give(&req.u.offset.resp->sem);
                }
                break;

            case REQ_CLEAR_AUDIO_DIR:
                LOG_DBG("[SD_WORK] Clearing audio directory");
                
                // Close data file before clearing
                fs_close(&fil_data);
                
                int unlink_res = fs_unlink(FILE_DATA_PATH);
                if (unlink_res != 0 && unlink_res != -ENOENT) {
                    LOG_ERR("[SD_WORK] Cannot unlink data file: %d", unlink_res);
                }
                
                fs_file_t_init(&fil_data);
                int reopen_res = fs_open(&fil_data, FILE_DATA_PATH, FS_O_CREATE | FS_O_RDWR);
                if (reopen_res == 0) {
                    fs_seek(&fil_data, 0, FS_SEEK_SET);
                } else {
                    LOG_ERR("[SD_WORK] open new data file failed: %d", reopen_res);
                    if (req.u.clear_dir.resp) {
                        req.u.clear_dir.resp->res = reopen_res;
                        k_sem_give(&req.u.clear_dir.resp->sem);
                    }
                    break;
                }
                
                current_file_size = 0;
                current_file_offset = 0;
                file_num_array[0] = 0;
                file_num_array[1] = 0;
                
                // Save offset 0 to info file
                fs_seek(&fil_info, 0, FS_SEEK_SET);
                uint32_t zero = 0;
                fs_write(&fil_info, &zero, sizeof(zero));
                fs_sync(&fil_info);
                
                if (req.u.clear_dir.resp) {
                    req.u.clear_dir.resp->res = 0;
                    k_sem_give(&req.u.clear_dir.resp->sem);
                }
                break;

            default:
                LOG_ERR("[SD_WORK] unknown req type: %d", req.type);
            }
        }
    }
}

/* Public API - Initialize SD card worker */
int sd_card_init(void)
{
    if (!sd_worker_tid) {
        sd_worker_tid = k_thread_create(&sd_worker_thread_data, sd_worker_stack, SD_WORKER_STACK_SIZE,
                                        (k_thread_entry_t)sd_worker_thread, NULL, NULL, NULL,
                                        SD_WORKER_PRIORITY, 0, K_NO_WAIT);
        k_thread_name_set(sd_worker_tid, "sd_worker");
    }
    return 0;
}

/* Backward compatibility - calls sd_card_init */
int mount_sd_card(void)
{
    return sd_card_init();
}

/* Public API - Get file size */
uint32_t get_file_size(void)
{
    return current_file_size;
}

/* Backward compatibility - get file size with num parameter (ignored) */
uint32_t get_file_size_num(uint8_t num)
{
    (void)num;
    return current_file_size;
}

/* Public API - Write to file via message queue */
uint32_t write_to_file(uint8_t *data, uint32_t length)
{
    if (length > MAX_WRITE_SIZE) {
        LOG_ERR("write_to_file: length %u exceeds MAX_WRITE_SIZE", length);
        return 0;
    }

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

/* Public API - Read audio data via message queue */
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

/* Public API - Save offset via message queue */
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

/* Public API - Get offset via message queue */
uint32_t get_offset(void)
{
    struct read_resp resp;
    k_sem_init(&resp.sem, 0, 1);

    uint32_t offset_val = 0;
    sd_req_t req = {0};
    req.type = REQ_READ_OFFSET;
    req.u.offset.resp = &resp;
    req.u.offset.out_offset = &offset_val;

    int ret = k_msgq_put(&sd_msgq, &req, K_MSEC(100));
    if (ret != 0) {
        LOG_ERR("Failed to queue get_offset request: %d", ret);
        return current_file_offset; // Return cached value on error
    }

    if (k_sem_take(&resp.sem, K_MSEC(5000)) != 0) {
        LOG_ERR("Timeout waiting for get_offset response");
        return current_file_offset; // Return cached value on timeout
    }

    return offset_val;
}

/* Public API - Clear audio directory via message queue */
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

    return 0;
}

/* DevKit power management - preserved from original */
void sd_off(void)
{
    // Close files before power off
    if (is_mounted) {
        fs_close(&fil_data);
        fs_close(&fil_info);
    }
    
    // Suspend SPI peripheral to save power
    const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi2));
    if (device_is_ready(spi_dev)) {
        pm_device_action_run(spi_dev, PM_DEVICE_ACTION_SUSPEND);
    }
    gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 15, GPIO_DISCONNECTED); // MOSI
    gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 14, GPIO_DISCONNECTED); // MISO  
    gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 13, GPIO_DISCONNECTED); // SCK
    gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio0)), 2, GPIO_DISCONNECTED);  // CS
    gpio_pin_set_dt(&sd_en_gpio_pin, 0);
    
    sd_enabled = false;
    is_mounted = false;
}

void sd_on(void)
{
    gpio_pin_set_dt(&sd_en_gpio_pin, 1);  
    gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 15, GPIO_OUTPUT);      // MOSI
    gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 14, GPIO_INPUT);       // MISO  
    gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 13, GPIO_OUTPUT);      // SCK
    gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio0)), 2, GPIO_OUTPUT_HIGH);  // CS
    const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi2));
    if (device_is_ready(spi_dev)) {
        pm_device_action_run(spi_dev, PM_DEVICE_ACTION_RESUME);
    }
    sd_enabled = true;
}

bool is_sd_on(void)
{
    return sd_enabled;
}

/* Deprecated functions - kept for backward compatibility */

int create_file(const char *file_path)
{
    snprintf(current_full_path, sizeof(current_full_path), "%s%s", disk_mount_pt, file_path);
    struct fs_file_t data_file;
    fs_file_t_init(&data_file);
    int ret = fs_open(&data_file, current_full_path, FS_O_WRITE | FS_O_CREATE);
    if (ret) {
        LOG_ERR("File creation failed %d", ret);
        return -2;
    }
    fs_close(&data_file);
    return 0;
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

int move_read_pointer(uint8_t num)
{
    char *read_ptr = generate_new_audio_header(num);
    if (read_ptr == NULL) {
        return -1;
    }
    snprintf(read_buffer_path, sizeof(read_buffer_path), "%s%s", disk_mount_pt, read_ptr);
    k_free(read_ptr);
    struct fs_dirent entry;
    int res = fs_stat(read_buffer_path, &entry);
    if (res) {
        LOG_ERR("invalid file in move read ptr");
        return -1;
    }
    return 0;
}

int move_write_pointer(uint8_t num)
{
    char *write_ptr = generate_new_audio_header(num);
    if (write_ptr == NULL) {
        return -1;
    }
    snprintf(write_buffer_path, sizeof(write_buffer_path), "%s%s", disk_mount_pt, write_ptr);
    k_free(write_ptr);
    struct fs_dirent entry;
    int res = fs_stat(write_buffer_path, &entry);
    if (res) {
        LOG_ERR("invalid file in move write pointer");
        return -1;
    }
    return 0;
}

int clear_audio_file(uint8_t num)
{
    // Just call clear_audio_directory for any file
    (void)num;
    return clear_audio_directory();
}
