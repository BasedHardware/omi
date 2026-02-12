#include "storage.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/fs/fs.h>

#include "sd_card.h"
#include "transport.h"
#include "utils.h"
#ifdef CONFIG_OMI_ENABLE_WIFI
#include "wifi.h"
#endif

LOG_MODULE_REGISTER(storage, CONFIG_LOG_DEFAULT_LEVEL);

/* Current file being read for transfer */
static char current_read_filename[MAX_FILENAME_LEN] = {0};
static uint32_t current_read_offset = 0;

#define MAX_PACKET_LENGTH 256
#define OPUS_ENTRY_LENGTH 80
#define FRAME_PREFIX_LENGTH 3

/* Legacy commands (backward compatible) */
#define READ_COMMAND 0
#define DELETE_COMMAND 1
#define NUKE 2
#define STOP_COMMAND 3

/* New multi-file sync commands */
#define CMD_LIST_FILES      0x10   // Get list of audio files
#define CMD_READ_FILE       0x11   // Read specific file: [cmd][file_index][offset:4]
#define CMD_DELETE_FILE     0x12   // Delete specific file: [cmd][file_index]

#define INVALID_FILE_SIZE 3
#define ZERO_FILE_SIZE 4
#define INVALID_COMMAND 6
#define FILE_NOT_FOUND 7
#define FILE_INDEX_OUT_OF_RANGE 8

#define MAX_HEARTBEAT_FRAMES 100
#define HEARTBEAT 50

/* Multi-file sync state */
static char sync_file_list[MAX_AUDIO_FILES][MAX_FILENAME_LEN];
static uint32_t sync_file_sizes[MAX_AUDIO_FILES];
static int sync_file_count = 0;
static int current_sync_file_index = -1;  /* -1 = legacy mode, >=0 = new protocol */
static uint8_t list_files_requested = 0;  /* Deferred to storage thread */
static int8_t delete_file_index = -1;     /* -1 = no delete, >=0 = file index to delete */
#ifdef CONFIG_OMI_ENABLE_WIFI
static uint8_t wifi_sync_all_requested = 0; /* Auto sync all files via WiFi */
#endif
static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t storage_write_handler(struct bt_conn *conn,
                                     const struct bt_gatt_attr *attr,
                                     const void *buf,
                                     uint16_t len,
                                     uint16_t offset,
                                     uint8_t flags);
#ifdef CONFIG_OMI_ENABLE_WIFI
static ssize_t storage_wifi_handler(struct bt_conn *conn,
                                    const struct bt_gatt_attr *attr,
                                    const void *buf,
                                    uint16_t len,
                                    uint16_t offset,
                                    uint8_t flags);
static void wifi_start_work_handler(struct k_work *work)
{
    mic_pause();
    wifi_turn_on();
}
#endif

static struct bt_uuid_128 storage_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295780, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_write_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295781, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_read_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295782, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_wifi_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295783, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static ssize_t storage_read_characteristic(struct bt_conn *conn,
                                           const struct bt_gatt_attr *attr,
                                           void *buf,
                                           uint16_t len,
                                           uint16_t offset);
static struct k_work wifi_start_work;

K_THREAD_STACK_DEFINE(storage_stack, 4096);
static struct k_thread storage_thread;

void broadcast_storage_packet(struct k_work *work_item);

static struct bt_gatt_attr storage_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&storage_service_uuid),
    BT_GATT_CHARACTERISTIC(&storage_write_uuid.uuid,
                           BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_WRITE,
                           NULL,
                           storage_write_handler,
                           NULL),
    BT_GATT_CCC(storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&storage_read_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ,
                           storage_read_characteristic,
                           NULL,
                           NULL),
    BT_GATT_CCC(storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
#ifdef CONFIG_OMI_ENABLE_WIFI
    BT_GATT_CHARACTERISTIC(&storage_wifi_uuid.uuid,
                           BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_WRITE,
                           NULL,
                           storage_wifi_handler,
                           NULL),
    BT_GATT_CCC(storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
#endif
};

struct bt_gatt_service storage_service = BT_GATT_SERVICE(storage_service_attr);

bool storage_is_on = false;

static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{

    storage_is_on = true;
    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_INF("Client subscribed for notifications");
    } else if (value == 0) {
        LOG_INF("Client unsubscribed from notifications");
    } else {
        LOG_ERR("Invalid CCC value: %u", value);
    }
}

static ssize_t storage_read_characteristic(struct bt_conn *conn,
                                           const struct bt_gatt_attr *attr,
                                           void *buf,
                                           uint16_t len,
                                           uint16_t offset)
{
    k_msleep(10);
    
    /* Get file statistics: total file count and total size */
    uint32_t file_count = 0;
    uint64_t total_size = 0;
    get_audio_file_stats(&file_count, &total_size);
    
    /* Get current offset info */
    char offset_filename[MAX_FILENAME_LEN] = {0};
    uint32_t offset_in_file = 0;
    get_offset(offset_filename, &offset_in_file);
    
    /* For backward compatibility, return total size and cumulative offset */
    uint32_t amount[2] = {0};
    amount[0] = (uint32_t)total_size;  // Total size of all files
    amount[1] = offset_in_file;         // Current offset in oldest file
    
    LOG_INF("Storage read requested: total size %u, offset %u, files %u", 
            amount[0], amount[1], file_count);
    ssize_t result = bt_gatt_attr_read(conn, attr, buf, len, offset, amount, 2 * sizeof(uint32_t));
    return result;
}

uint8_t transport_started = 0;
#define SD_BLE_SIZE 440
#define TCP_CHUNK_COUNT 10
#define STORAGE_BUFFER_SIZE (SD_BLE_SIZE * TCP_CHUNK_COUNT + 5 * TCP_CHUNK_COUNT)  /* Restore safe size ~4.5KB */
static uint8_t storage_buffer[STORAGE_BUFFER_SIZE];  /* Shared buffer for BLE and WiFi */
static uint32_t offset = 0;
static uint8_t stop_started = 0;
static uint8_t delete_started = 0;
uint32_t remaining_length = 0;

static int setup_storage_tx()
{
    transport_started = (uint8_t) 0;
    LOG_INF("about to transmit storage");
    k_msleep(1000);

    int file_count = 0;
    int ret = get_audio_file_list(sync_file_list, MAX_AUDIO_FILES, &file_count);
    if (ret < 0 || file_count == 0) {
        LOG_ERR("No audio files available");
        remaining_length = 0;
        return -1;
    }
    
    /* Get current offset info to find where we left off */
    char offset_filename[MAX_FILENAME_LEN] = {0};
    uint32_t offset_in_file = 0;
    get_offset(offset_filename, &offset_in_file);
    
    /* Find the file to start reading from */
    int start_file_idx = 0;
    if (offset_filename[0] != '\0') {
        for (int i = 0; i < file_count; i++) {
            if (strcmp(sync_file_list[i], offset_filename) == 0) {
                start_file_idx = i;
                break;
            }
        }
    }
    
    /* Use the oldest unread file or the specified offset file */
    strncpy(current_read_filename, sync_file_list[start_file_idx], MAX_FILENAME_LEN - 1);
    current_read_offset = (start_file_idx == 0 && offset_filename[0] != '\0') ? offset_in_file : 0;
    
    /* If a specific offset was requested, use it */
    if (offset > 0) {
        current_read_offset = offset - (offset % SD_BLE_SIZE);
    }
    
    /* Calculate total remaining data across all files from current position */
    uint32_t file_count_tmp = 0;
    uint64_t all_files_size = 0;
    get_audio_file_stats(&file_count_tmp, &all_files_size);
    
    /* For simplicity, calculate remaining from current file */
    /* In a full implementation, we'd track across multiple files */
    struct fs_dirent file_stat;
    char file_path[64];
    snprintf(file_path, sizeof(file_path), "/SD:/audio/%s", current_read_filename);
    if (fs_stat(file_path, &file_stat) == 0) {
        remaining_length = file_stat.size - current_read_offset;
    } else {
        remaining_length = 0;
    }
    
    LOG_INF("remaining length: %d", remaining_length);
    LOG_INF("current file: %s, offset: %d", current_read_filename, current_read_offset);

    return 0;
}

uint8_t nuke_started = 0;
static uint8_t heartbeat_count = 0;

/**
 * @brief Refresh file list cache for multi-file sync
 */
static int refresh_file_list_cache(void)
{
    int ret = get_audio_file_list(sync_file_list, MAX_AUDIO_FILES, &sync_file_count);
    if (ret < 0) {
        LOG_ERR("Failed to get file list: %d", ret);
        sync_file_count = 0;
        return ret;
    }
    
    /* Get file sizes */
    char current_name[MAX_FILENAME_LEN] = {0};
    /* If we can read the currently open filename, we will prefer in-memory size for it */
    (void)get_current_filename(current_name, sizeof(current_name));
    for (int i = 0; i < sync_file_count; i++) {
        char file_path[64];
        snprintf(file_path, sizeof(file_path), "/SD:/audio/%s", sync_file_list[i]);
        struct fs_dirent file_stat;
        if (fs_stat(file_path, &file_stat) == 0) {
            sync_file_sizes[i] = file_stat.size;
        } else {
            sync_file_sizes[i] = 0;
        }
        /* If this is the currently recording file, use the live size */
        if (current_name[0] != '\0' && strcmp(sync_file_list[i], current_name) == 0) {
            uint32_t live_sz = get_file_size();
            if (live_sz > sync_file_sizes[i]) {
                sync_file_sizes[i] = live_sz;
            }
        }
    }
    
    LOG_INF("File list refreshed: %d files", sync_file_count);
    return sync_file_count;
}

/**
 * @brief Send file list response
 * Format: [count:1][ts1:4][sz1:4][ts2:4][sz2:4]...
 */
static int send_file_list_response(struct bt_conn *conn)
{
    if (refresh_file_list_cache() < 0) {
        uint8_t error_resp[1] = {0xFF};
        bt_gatt_notify(conn, &storage_service.attrs[1], error_resp, 1);
        return -1;
    }
    
    /* Use storage_buffer to build response (max 4440 bytes) */
    /* Each file: ts(4) + size(4) = 8 bytes, max ~550 files */
    int resp_len = 0;
    
    storage_buffer[resp_len++] = (uint8_t)sync_file_count;
    
    for (int i = 0; i < sync_file_count && resp_len + 8 <= STORAGE_BUFFER_SIZE; i++) {
        uint32_t timestamp = (uint32_t)strtoul(sync_file_list[i], NULL, 16);
        uint32_t size = sync_file_sizes[i];
        
        storage_buffer[resp_len++] = (timestamp >> 24) & 0xFF;
        storage_buffer[resp_len++] = (timestamp >> 16) & 0xFF;
        storage_buffer[resp_len++] = (timestamp >> 8) & 0xFF;
        storage_buffer[resp_len++] = timestamp & 0xFF;
        
        storage_buffer[resp_len++] = (size >> 24) & 0xFF;
        storage_buffer[resp_len++] = (size >> 16) & 0xFF;
        storage_buffer[resp_len++] = (size >> 8) & 0xFF;
        storage_buffer[resp_len++] = size & 0xFF;
    }
    
    LOG_INF("Sending file list: %d files, %d bytes", sync_file_count, resp_len);
    return bt_gatt_notify(conn, &storage_service.attrs[1], storage_buffer, resp_len);
}

/**
 * @brief Setup transfer for specific file by index
 */
static int setup_file_transfer(int file_index, uint32_t start_offset)
{
    if (file_index < 0 || file_index >= sync_file_count) {
        LOG_ERR("File index out of range: %d", file_index);
        return -1;
    }
    
    strncpy(current_read_filename, sync_file_list[file_index], MAX_FILENAME_LEN - 1);
    current_read_offset = start_offset - (start_offset % SD_BLE_SIZE);
    current_sync_file_index = file_index;
    
    if (current_read_offset < sync_file_sizes[file_index]) {
        remaining_length = sync_file_sizes[file_index] - current_read_offset;
    } else {
        remaining_length = 0;
    }
    
    LOG_INF("Setup transfer: file[%d]=%s, offset=%u, remaining=%u", 
            file_index, current_read_filename, current_read_offset, remaining_length);
    return 0;
}

/**
 * @brief Delete specific file by index
 */
static int delete_file_by_index(int file_index)
{
    if (file_index < 0 || file_index >= sync_file_count) {
        return -1;
    }
    /* Copy target filename so we are robust to list refreshes */
    char target_name[MAX_FILENAME_LEN] = {0};
    strncpy(target_name, sync_file_list[file_index], MAX_FILENAME_LEN - 1);

    /* Delegate deletion to SD worker so it can safely handle
     * the case where this is the currently-recording file. */
    int ret = delete_audio_file(target_name);
    if (ret < 0) {
        LOG_ERR("Failed to delete file[%d]: %s (err=%d)", file_index, target_name, ret);
        return ret;
    }

    LOG_INF("Deleted file[%d]: %s", file_index, target_name);
    refresh_file_list_cache();
    return 0;
}

static uint8_t parse_storage_command(void *buf, uint16_t len, struct bt_conn *conn)
{
    if (len < 1) {
        return INVALID_COMMAND;
    }
    
    const uint8_t command = ((uint8_t *) buf)[0];
    LOG_INF("Storage command: 0x%02X, len=%d", command, len);
    
    /* ===== NEW MULTI-FILE COMMANDS ===== */
    
    if (command == CMD_LIST_FILES) {
        list_files_requested = 1;  /* Defer to storage thread to avoid stack overflow */
        return 0xFF;  /* Will be processed in storage thread */
    }
    
    if (command == CMD_READ_FILE) {
        if (len < 2) return INVALID_COMMAND;
        
        uint8_t file_index = ((uint8_t *) buf)[1];
        uint32_t request_offset = 0;
        if (len >= 6) {
            request_offset = ((uint8_t *) buf)[2] << 24 | ((uint8_t *) buf)[3] << 16 | 
                            ((uint8_t *) buf)[4] << 8 | ((uint8_t *) buf)[5];
        }
        
        if (sync_file_count == 0) refresh_file_list_cache();
        
        if (file_index >= sync_file_count) {
            return FILE_INDEX_OUT_OF_RANGE;
        }
        
        if (setup_file_transfer(file_index, request_offset) < 0) {
            return FILE_NOT_FOUND;
        }
        
        transport_started = 1;
        return 0;
    }
    
    if (command == CMD_DELETE_FILE) {
        if (len < 2) return INVALID_COMMAND;
        
        uint8_t file_index = ((uint8_t *) buf)[1];
        if (sync_file_count == 0) {
            /* File list not cached, defer refresh + delete to storage thread */
            delete_file_index = file_index;
            return 0xFF;
        }
        if (file_index >= sync_file_count) {
            return FILE_INDEX_OUT_OF_RANGE;
        }
        
        delete_file_index = file_index;  /* Defer to storage thread */
        return 0xFF;
    }
    
    /* ===== LEGACY COMMANDS ===== */
    
    if (len != 6 && len != 2) {
        LOG_INF("invalid legacy command");
        return INVALID_COMMAND;
    }
    
    const uint8_t file_num = ((uint8_t *) buf)[1];
    uint32_t request_offset = 0;
    if (len == 6) {
        request_offset = ((uint8_t *) buf)[2] << 24 | ((uint8_t *) buf)[3] << 16 | 
                        ((uint8_t *) buf)[4] << 8 | ((uint8_t *) buf)[5];
    }
    LOG_INF("Legacy cmd: %d file: %d offset: %d", command, file_num, request_offset);

    if (command == READ_COMMAND && file_num != 1) {
        return INVALID_FILE_SIZE;
    }

    if (command == READ_COMMAND) {
        current_sync_file_index = -1;  /* Legacy mode - no timestamp prefix */
        uint32_t file_size = get_file_size();
        if (request_offset >= file_size) {
            return INVALID_FILE_SIZE;
        } else if (file_size == 0) {
            return ZERO_FILE_SIZE;
        } else {
            offset = request_offset - (request_offset % SD_BLE_SIZE);
            transport_started = 1;
        }
    } else if (command == DELETE_COMMAND) {
        delete_started = 1;
    } else if (command == NUKE) {
        nuke_started = 1;
    } else if (command == STOP_COMMAND) {
        storage_stop_transfer();
    } else if (command == HEARTBEAT) {
        heartbeat_count = 0;
    } else {
        return INVALID_COMMAND;
    }
    return 0;
}

static ssize_t storage_write_handler(struct bt_conn *conn,
                                     const struct bt_gatt_attr *attr,
                                     const void *buf,
                                     uint16_t len,
                                     uint16_t offset,
                                     uint8_t flags)
{
    LOG_INF("about to schedule the storage");
    LOG_INF("was sent %d  ", ((uint8_t *) buf)[0]);

    uint8_t result = parse_storage_command((void *)buf, len, conn);
    
    /* 0xFF means response was already sent */
    if (result != 0xFF) {
        uint8_t result_buffer[1] = {result};
        LOG_INF("length of storage write: %d, result: %d", len, result);
        bt_gatt_notify(conn, &storage_service.attrs[1], &result_buffer, 1);
    }
    
    k_msleep(500);
    return len;
}

#ifdef CONFIG_OMI_ENABLE_WIFI
static ssize_t storage_wifi_handler(struct bt_conn *conn,
                                    const struct bt_gatt_attr *attr,
                                    const void *buf,
                                    uint16_t len,
                                    uint16_t offset,
                                    uint8_t flags)
{
    uint8_t result_buffer[1] = {0};
    LOG_INF("wifi config write handler called");

    if (len < 1) {
        result_buffer[0] = 1; // error: invalid length
        bt_gatt_notify(conn, &storage_service.attrs[8], &result_buffer, 1);
        return len;
    }

    if (wifi_is_hw_available() == false) {
        LOG_ERR("Wi-Fi hardware not available");
        result_buffer[0] = 0xFE; // error: hardware not available
        bt_gatt_notify(conn, &storage_service.attrs[8], &result_buffer, 1);
        return len;
    }

    const uint8_t cmd = ((const uint8_t *) buf)[0];

    switch (cmd) {
        case 0x01: // WIFI_SETUP
            LOG_INF("WIFI_SETUP: len=%d", len);
            if (len < 2) {
                LOG_WRN("WIFI_SETUP: invalid setup length: len=%d", len);
                result_buffer[0] = 2; // error: invalid setup length
                break;
            }
            // Parse SSID
            // Format: [cmd][ssid_len][ssid][password_len][password]
            uint8_t idx = 1;
            uint8_t ssid_len = ((const uint8_t *)buf)[idx++];
            LOG_INF("WIFI_SETUP: ssid_len=%d, len=%d", ssid_len, len);

            if (ssid_len == 0 || ssid_len > WIFI_MAX_SSID_LEN || idx + ssid_len > len) {
                LOG_WRN("SSID length invalid: ssid_len=%d, len=%d", ssid_len, len);
                result_buffer[0] = 3; break;
            }
            char ssid[WIFI_MAX_SSID_LEN + 1] = {0};
            memcpy(ssid, &((const uint8_t *)buf)[idx], ssid_len);
            idx += ssid_len;
            LOG_INF("WIFI_SETUP: ssid='%s'", ssid);

            uint8_t pwd_len = ((const uint8_t *)buf)[idx++];
            if (pwd_len < WIFI_MIN_PASSWORD_LEN || pwd_len > WIFI_MAX_PASSWORD_LEN || idx + pwd_len > len) {
                LOG_WRN("PWD length invalid: pwd_len=%d, len=%d", pwd_len, len);
                result_buffer[0] = 4; break;
            }
            char pwd[WIFI_MAX_PASSWORD_LEN + 1] = {0};
            if (pwd_len > 0) memcpy(pwd, &((const uint8_t *)buf)[idx], pwd_len);
            LOG_INF("WIFI_SETUP: pwd='%s' pwd_len=%d, len=%d", pwd, pwd_len, len);

            setup_wifi_credentials(ssid, pwd);
            result_buffer[0] = 0; // success
            break;

        case 0x02: // WIFI_START
            LOG_INF("WIFI_START command received");
            if (is_wifi_on()) {
                LOG_INF("Wi-Fi already on - wait for next session");
                result_buffer[0] = 5; // wait for next session
                break;
            }
            wifi_sync_all_requested = 1;  /* Will auto sync all files */
            k_work_submit(&wifi_start_work);
            result_buffer[0] = 0;
            break;

        case 0x03: // WIFI_SHUTDOWN
            LOG_INF("WIFI_SHUTDOWN command received");
            storage_stop_transfer();
            wifi_turn_off();
            mic_resume();
            result_buffer[0] = 0;
            break;

        case 0x04: // WIFI_DELETE_ALL - Delete all synced files
            LOG_INF("WIFI_DELETE_ALL command received");
            storage_stop_transfer();
            {
                int err = clear_audio_directory();
                if (err) {
                    LOG_ERR("Failed to clear audio directory: %d", err);
                    result_buffer[0] = 0x10; // error: delete failed
                } else {
                    LOG_INF("All audio files deleted successfully");
                    result_buffer[0] = 0; // success
                }
            }
            break;

        default:
            LOG_WRN("Unknown WIFI command: %d", cmd);
            result_buffer[0] = 0xFF; // unknown command
            break;
    }

    bt_gatt_notify(conn, &storage_service.attrs[8], &result_buffer, 1);
    return len;
}
#endif

static void write_to_gatt(struct bt_conn *conn)
{
    uint32_t packet_size = MIN(remaining_length, SD_BLE_SIZE);
    
    int err;
    
    /* New protocol: add 4-byte timestamp prefix */
    if (current_sync_file_index >= 0) {
        uint32_t timestamp = (uint32_t)strtoul(sync_file_list[current_sync_file_index], NULL, 16);
        
        /* Build packet in storage_buffer: [timestamp:4][audio_data:440] = 444 bytes */
        storage_buffer[0] = (timestamp >> 24) & 0xFF;
        storage_buffer[1] = (timestamp >> 16) & 0xFF;
        storage_buffer[2] = (timestamp >> 8) & 0xFF;
        storage_buffer[3] = timestamp & 0xFF;
        
        int r = read_audio_data(current_read_filename, storage_buffer + 4, packet_size, current_read_offset);
        if (r < 0) {
            LOG_ERR("Failed to read audio data: %d", r);
            remaining_length = 0;
            return;
        }
        
        err = bt_gatt_notify(conn, &storage_service.attrs[1], storage_buffer, 4 + packet_size);
    } else {
        /* Legacy: raw audio data without timestamp */
        int r = read_audio_data(current_read_filename, storage_buffer, packet_size, current_read_offset);
        if (r < 0) {
            LOG_ERR("Failed to read audio data: %d", r);
            remaining_length = 0;
            return;
        }
        
        err = bt_gatt_notify(conn, &storage_service.attrs[1], storage_buffer, packet_size);
    }
    
    current_read_offset = current_read_offset + packet_size;
    offset = current_read_offset;
    
    if (err) {
        LOG_PRINTK("error writing to gatt: %d\n", err);
    } else {
        remaining_length = remaining_length - packet_size;
    }
}

#ifdef CONFIG_OMI_ENABLE_WIFI
static void write_to_tcp()
{
    /* Use valid storage buffer capacity for one large packet */
    /* Protocol V2: [idx:1][ts:4][len:2][data:len] */
    uint32_t max_payload = STORAGE_BUFFER_SIZE - 7;
    uint32_t to_read = MIN(remaining_length, max_payload);
    
    /* New protocol: build packets with file_index + timestamp prefix */
    if (current_sync_file_index >= 0) {
        uint32_t timestamp = (uint32_t)strtoul(sync_file_list[current_sync_file_index], NULL, 16);
        uint8_t file_idx = (uint8_t)current_sync_file_index;
        
        /* 1. Read audio data directly into storage_buffer payload area */
        int ret = read_audio_data(current_read_filename, storage_buffer + 7, to_read, current_read_offset);
        if (ret <= 0) {
            LOG_ERR("Failed to read audio data or EOF: %d", ret);
            remaining_length = 0;  /* Force move to next file */
            return;
        }
        
        /* Adjust to_read if we hit EOF or read less */
        to_read = ret;
        
        /* 2. Create Header: [idx][ts][len] */
        storage_buffer[0] = file_idx;
        storage_buffer[1] = (timestamp >> 24) & 0xFF;
        storage_buffer[2] = (timestamp >> 16) & 0xFF;
        storage_buffer[3] = (timestamp >> 8) & 0xFF;
        storage_buffer[4] = timestamp & 0xFF;
        storage_buffer[5] = (to_read >> 8) & 0xFF;
        storage_buffer[6] = to_read & 0xFF;
        
        uint32_t packet_len = 7 + to_read;
        
        current_read_offset += to_read;
        offset = current_read_offset;
        remaining_length -= to_read;
        
        /* Send packet */
        size_t sent = 0;
        while (sent < packet_len && is_wifi_on()) {
            int n = wifi_send_data(storage_buffer + sent, packet_len - sent);
            if (n <= 0) { k_msleep(10); } else { sent += n; k_yield(); }
        }
    } else {
        /* Legacy: raw audio data without timestamp */
        uint32_t legacy_chunk = MIN(remaining_length, SD_BLE_SIZE * 10); /* Keep legacy size reasonable */
        int ret = read_audio_data(current_read_filename, storage_buffer, legacy_chunk, current_read_offset);
        if (ret > 0) {
            current_read_offset += ret;
            offset = current_read_offset;
            remaining_length -= ret;
            
            size_t sent = 0;
            while ((sent < ret) && is_wifi_on()) {
                int n = wifi_send_data(storage_buffer + sent, ret - sent);
                if (n <= 0) { k_msleep(10); } else { sent += n; k_yield(); }
            }
        } else {
            LOG_ERR("Failed to read audio data: %d", ret);
            remaining_length = 0;
        }
    }
}
#endif


void storage_stop_transfer()
{
    remaining_length = 0;
    stop_started = 1;
}

void storage_write(void)
{
    uint32_t total_sent = 0;
    uint32_t consecutive_errors = 0;

    while (1) {
        struct bt_conn *conn = get_current_connection();

        if (transport_started) {
            LOG_INF("transport started in side : %d", transport_started);
            /* Only call legacy setup for legacy mode (current_sync_file_index == -1)
             * New protocol (CMD_READ_FILE) already set up via setup_file_transfer() */
            if (current_sync_file_index < 0) {
                setup_storage_tx();
            }
            transport_started = 0;  /* Clear flag after setup */
        }
        // probably prefer to implement using work orders for delete,nuke,etc...
        if (delete_started) {
            LOG_INF("delete:%d\n", delete_started);
            int err = clear_audio_directory();

            if (err) {
                LOG_PRINTK("error clearing\n");
            } else {
                offset = 0;
                uint8_t result_buffer[1] = {200};
                if (conn) {
                    bt_gatt_notify(get_current_connection(), &storage_service.attrs[1], &result_buffer, 1);
                }
            }
            delete_started = 0;
            k_msleep(10);
        }
        if (nuke_started) {
            clear_audio_directory();
            offset = 0;
            nuke_started = 0;
        }
        if (list_files_requested) {
            list_files_requested = 0;
            if (conn) {
                send_file_list_response(conn);
            }
        }
#ifdef CONFIG_OMI_ENABLE_WIFI
        /* WiFi sync all: setup first file when WiFi is ready */
        if (wifi_sync_all_requested && is_wifi_on() && is_wifi_transport_ready()) {
            wifi_sync_all_requested = 0;
            LOG_INF("WiFi ready - starting sync all files");
            
            /* Refresh file list and start from first file */
            refresh_file_list_cache();
            if (sync_file_count > 0) {
                /* Send header packet first: [0xFF][count:1][ts1:4][sz1:4]... */
                int hdr_len = 0;
                storage_buffer[hdr_len++] = 0xFF;  /* Magic byte for header */
                storage_buffer[hdr_len++] = (uint8_t)sync_file_count;
                
                for (int i = 0; i < sync_file_count && hdr_len + 8 <= STORAGE_BUFFER_SIZE; i++) {
                    uint32_t ts = (uint32_t)strtoul(sync_file_list[i], NULL, 16);
                    uint32_t sz = sync_file_sizes[i];
                    storage_buffer[hdr_len++] = (ts >> 24) & 0xFF;
                    storage_buffer[hdr_len++] = (ts >> 16) & 0xFF;
                    storage_buffer[hdr_len++] = (ts >> 8) & 0xFF;
                    storage_buffer[hdr_len++] = ts & 0xFF;
                    storage_buffer[hdr_len++] = (sz >> 24) & 0xFF;
                    storage_buffer[hdr_len++] = (sz >> 16) & 0xFF;
                    storage_buffer[hdr_len++] = (sz >> 8) & 0xFF;
                    storage_buffer[hdr_len++] = sz & 0xFF;
                }
                
                LOG_INF("Sending WiFi header: %d files, %d bytes", sync_file_count, hdr_len);
                size_t sent = 0;
                while (sent < hdr_len && is_wifi_on()) {
                    int n = wifi_send_data(storage_buffer + sent, hdr_len - sent);
                    if (n <= 0) { k_msleep(10); } else { sent += n; }
                }
                k_msleep(100);  /* Give app time to process header */
                
                /* Find first non-empty file */
                int start_idx = 0;
                while (start_idx < sync_file_count && sync_file_sizes[start_idx] == 0) {
                    LOG_INF("WiFi sync: skipping empty file %d/%d", start_idx + 1, sync_file_count);
                    start_idx++;
                }
                
                if (start_idx < sync_file_count) {
                    current_sync_file_index = start_idx;
                    setup_file_transfer(start_idx, 0);
                } else {
                    LOG_INF("WiFi sync: all files are empty, nothing to sync");
                    current_sync_file_index = -1;
                }
            } else {
                LOG_INF("No files to sync");
            }
        }
#endif
        if (delete_file_index >= 0) {
            int8_t idx = delete_file_index;
            delete_file_index = -1;
            
            /* Ensure file list is cached */
            if (sync_file_count == 0) {
                refresh_file_list_cache();
            }
            
            uint8_t result = 0;
            if (idx >= sync_file_count) {
                result = FILE_INDEX_OUT_OF_RANGE;
            } else if (delete_file_by_index(idx) < 0) {
                result = FILE_NOT_FOUND;
            }
            
            if (conn) {
                bt_gatt_notify(conn, &storage_service.attrs[1], &result, 1);
            }
            LOG_INF("Delete file[%d] result: %d", idx, result);
        }
        if (stop_started) {
            remaining_length = 0;
            stop_started = 0;
            save_offset(current_read_filename, current_read_offset);
        }
        if (heartbeat_count == MAX_HEARTBEAT_FRAMES) {
            LOG_INF("no heartbeat sent");
            save_offset(current_read_filename, current_read_offset);
            // ensure heartbeat count resets
            heartbeat_count = 0;
        }

        if (remaining_length > 0) {
            if (conn == NULL
#ifdef CONFIG_OMI_ENABLE_WIFI
                && !is_wifi_on()
#endif
            ) {
                LOG_ERR("invalid connection");
                remaining_length = 0;
                save_offset(current_read_filename, current_read_offset);
                // save offset to flash
                continue;
                // k_yield();
            }

#ifdef CONFIG_OMI_ENABLE_WIFI
            // Send data over TCP if WiFi is ready, otherwise over GATT
            if (is_wifi_on()) {
                if (is_wifi_transport_ready()) {
                    write_to_tcp();
                    heartbeat_count = (heartbeat_count + 1) % (MAX_HEARTBEAT_FRAMES + 1);
                }
            } else
#endif
            {
                write_to_gatt(conn);
                heartbeat_count = (heartbeat_count + 1) % (MAX_HEARTBEAT_FRAMES + 1);
            }

            transport_started = 0;
            if (remaining_length == 0) {
                if (stop_started) {
                    stop_started = 0;
                } else {
                    save_offset(current_read_filename, current_read_offset);
                    LOG_INF("File done: %s", current_read_filename);
                    
#ifdef CONFIG_OMI_ENABLE_WIFI
                    /* WiFi sync: auto continue to next file */
                    if (is_wifi_on() && current_sync_file_index >= 0) {
                        int next_idx = current_sync_file_index + 1;
                        
                        /* Skip files with 0 bytes */
                        while (next_idx < sync_file_count && sync_file_sizes[next_idx] == 0) {
                            LOG_INF("WiFi sync: skipping empty file %d/%d", next_idx + 1, sync_file_count);
                            next_idx++;
                        }
                        
                        if (next_idx < sync_file_count) {
                            LOG_INF("WiFi sync: moving to file %d/%d", next_idx + 1, sync_file_count);
                            setup_file_transfer(next_idx, 0);
                        } else {
                            LOG_INF("WiFi sync complete! All %d files synced", sync_file_count);
                            current_sync_file_index = -1;
                            /* WiFi will auto shutdown after idle timeout */
                        }
                    } else
#endif
                    {
                        /* BLE: notify completion */
                        LOG_PRINTK("done. attempting to download more files\n");
                        uint8_t stop_result[1] = {100};
                        int err = bt_gatt_notify(get_current_connection(), &storage_service.attrs[1], &stop_result, 1);
                        k_msleep(10);
                    }
                }
            }
        }

        // Sleep when there's no work
        if (remaining_length == 0 && !delete_started && !nuke_started && !stop_started) {
            k_msleep(10);
        } else {
            k_yield();
        }
    }
}

int storage_init()
{
#ifdef CONFIG_OMI_ENABLE_WIFI
    k_work_init(&wifi_start_work, wifi_start_work_handler);
#endif
    k_thread_create(&storage_thread,
                    storage_stack,
                    K_THREAD_STACK_SIZEOF(storage_stack),
                    (k_thread_entry_t) storage_write,
                    NULL,
                    NULL,
                    NULL,
                    K_PRIO_PREEMPT(7),
                    0,
                    K_NO_WAIT);
    return 0;
}
