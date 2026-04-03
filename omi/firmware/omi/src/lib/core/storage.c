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

#include "sd_card.h"
#include "transport.h"
#include "utils.h"

LOG_MODULE_REGISTER(storage, CONFIG_LOG_DEFAULT_LEVEL);

/* Current file being read for transfer */
static char current_read_filename[MAX_FILENAME_LEN] = {0};
static uint32_t current_read_offset = 0;

#define MAX_PACKET_LENGTH 256
#define OPUS_ENTRY_LENGTH 80
#define FRAME_PREFIX_LENGTH 3

/* Control commands */
#define CMD_STOP_SYNC      0x03

/* New multi-file sync commands */
#define CMD_LIST_FILES      0x10   // Get list of audio files
#define CMD_READ_FILE       0x11   // Read specific file: [cmd][file_index][offset:4]
#define CMD_DELETE_FILE     0x12   // Delete specific file: [cmd][file_index]

#define INVALID_COMMAND 6
#define FILE_NOT_FOUND 7
#define FILE_INDEX_OUT_OF_RANGE 8

#define MAX_HEARTBEAT_FRAMES 100
#define HEARTBEAT 50

/* Multi-file sync state */
static char sync_file_list[MAX_AUDIO_FILES][MAX_FILENAME_LEN];
static uint32_t sync_file_sizes[MAX_AUDIO_FILES];
static int sync_file_count = 0;
static int current_sync_file_index = -1;
static uint8_t list_files_requested = 0;  /* Deferred to storage thread */
static int8_t delete_file_index = -1;     /* -1 = no delete, >=0 = file index to delete */

static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t storage_write_handler(struct bt_conn *conn,
                                     const struct bt_gatt_attr *attr,
                                     const void *buf,
                                     uint16_t len,
                                     uint16_t offset,
                                     uint8_t flags);

static struct bt_uuid_128 storage_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295780, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_write_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295781, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_read_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295782, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static ssize_t storage_read_characteristic(struct bt_conn *conn,
                                           const struct bt_gatt_attr *attr,
                                           void *buf,
                                           uint16_t len,
                                           uint16_t offset);

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
};

struct bt_gatt_service storage_service = BT_GATT_SERVICE(storage_service_attr);

#define STORAGE_IDLE_POLL_MS_OFFLINE 2000
#define STORAGE_IDLE_POLL_MS_CONNECTED 1

#define STORAGE_WRITE_NOTIFY_ATTR_IDX 2

bool storage_is_on = false;
static uint32_t cached_file_count = 0;
static uint64_t cached_total_size = 0;
static int64_t storage_stats_next_refresh_ms = 0;

static bool storage_notify_ready(struct bt_conn *conn)
{
    return conn && bt_gatt_is_subscribed(conn,
                                         &storage_service.attrs[STORAGE_WRITE_NOTIFY_ATTR_IDX],
                                         BT_GATT_CCC_NOTIFY);
}

static int storage_notify(struct bt_conn *conn, const void *data, uint16_t len)
{
    if (!storage_notify_ready(conn)) {
        return -EAGAIN;
    }

    return bt_gatt_notify(conn, &storage_service.attrs[STORAGE_WRITE_NOTIFY_ATTR_IDX], data, len);
}

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
    int64_t now = k_uptime_get();
    if (now >= storage_stats_next_refresh_ms) {
        uint32_t file_count = 0;
        uint64_t total_size = 0;
        if (get_audio_file_stats(&file_count, &total_size) == 0) {
            cached_file_count = file_count;
            cached_total_size = total_size;
            storage_stats_next_refresh_ms = now + 2000;
        } else {
            storage_stats_next_refresh_ms = now + 500;
        }
    }
    
    /* Phone app expects (little-endian):
     *   [0..3]  total_used_bytes  (uint32)
     *   [4..7]  file_count        (uint32)
     *   [8..11] free_bytes        (uint32)  — optional, newer firmware
     *   [12..15] status_flags     (uint32)  — optional, newer firmware
     */
    uint32_t payload[4] = {0};
    payload[0] = (uint32_t)cached_total_size;   /* total used bytes */
    payload[1] = cached_file_count;             /* number of audio files */
    payload[2] = 0;                      /* free_bytes — TODO: implement disk_access_ioctl */
    payload[3] = 0;                      /* status_flags: bit0=charging, bit1=warning, bit2=error */
    
    LOG_INF("Storage read: used=%u bytes, files=%u", payload[0], payload[1]);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, payload, sizeof(payload));
}

uint8_t transport_started = 0;
#define SD_BLE_SIZE 440
#define STORAGE_CHUNK_COUNT 20
#define STORAGE_BUFFER_SIZE (SD_BLE_SIZE * STORAGE_CHUNK_COUNT + 5 * STORAGE_CHUNK_COUNT)  /* ~8.9KB */
static uint8_t storage_buffer[STORAGE_BUFFER_SIZE];
static uint8_t stop_started = 0;
uint32_t remaining_length = 0;

#define SYNC_SPEED_LOG_INTERVAL_MS (30 * 1000)

typedef enum {
    SYNC_SPEED_MODE_NONE = 0,
    SYNC_SPEED_MODE_BLE,
} sync_speed_mode_t;

static sync_speed_mode_t sync_speed_mode = SYNC_SPEED_MODE_NONE;
static int64_t sync_speed_window_start_ms = 0;
static uint64_t sync_speed_window_bytes = 0;

static void sync_speed_reset(sync_speed_mode_t mode)
{
    sync_speed_mode = mode;
    sync_speed_window_start_ms = k_uptime_get();
    sync_speed_window_bytes = 0;
}

static void sync_speed_add_bytes(uint32_t bytes)
{
    if (sync_speed_mode == SYNC_SPEED_MODE_NONE || bytes == 0) {
        return;
    }

    sync_speed_window_bytes += bytes;
    int64_t now = k_uptime_get();
    int64_t elapsed_ms = now - sync_speed_window_start_ms;

    if (elapsed_ms >= SYNC_SPEED_LOG_INTERVAL_MS) {
        uint64_t kbps = (sync_speed_window_bytes * 1000U) / (elapsed_ms * 1024U);
        const char *mode_str = "BLE";
        LOG_INF("Sync speed (%s): %u KB/s", mode_str, (uint32_t)kbps);

        sync_speed_window_start_ms = now;
        sync_speed_window_bytes = 0;
    }
}

static uint16_t get_ble_chunk_size(struct bt_conn *conn, uint8_t include_timestamp)
{
    if (!conn) {
        return SD_BLE_SIZE;
    }

    uint16_t mtu = bt_gatt_get_mtu(conn);
    if (mtu <= 3) {
        return 20;
    }

    uint16_t att_payload = mtu - 3;
    uint16_t protocol_overhead = include_timestamp ? 4 : 0;

    if (att_payload <= protocol_overhead + 8) {
        return 20;
    }

    uint16_t chunk = att_payload - protocol_overhead;
    return MIN(chunk, (uint16_t)SD_BLE_SIZE);
}

static uint8_t heartbeat_count = 0;

/**
 * @brief Refresh file list cache for multi-file sync
 */
static int refresh_file_list_cache(void)
{
    int ret = get_audio_file_list_with_sizes(sync_file_list, sync_file_sizes,
                                             MAX_AUDIO_FILES, &sync_file_count);
    if (ret < 0) {
        LOG_ERR("Failed to get file list: %d", ret);
        sync_file_count = 0;
        return ret;
    }
    
    LOG_INF("File list refreshed: %d files", sync_file_count);
    return sync_file_count;
}

/**
 * @brief Send file list response
 * Format: [count:1][ts1:4][sz1:4][ts2:4][sz2:4]...
 *
 * Assumes the file list cache (sync_file_list/sync_file_sizes/sync_file_count)
 * has already been populated by the caller via refresh_file_list_cache().
 * Refreshes only when the cache is empty (sync_file_count == 0).
 */
static int send_file_list_response(struct bt_conn *conn)
{
    if (sync_file_count == 0 && refresh_file_list_cache() < 0) {
        uint8_t error_resp[1] = {0xFF};
        storage_notify(conn, error_resp, 1);
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
    return storage_notify(conn, storage_buffer, resp_len);
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
    current_read_offset = start_offset;
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

    /* Control commands */
    if (command == CMD_STOP_SYNC) {
        storage_stop_transfer();
        return 0;
    }

    if (command == HEARTBEAT) {
        heartbeat_count = 0;
        return 0;
    }

    /* Accept only multi-file protocol commands above. */
    return INVALID_COMMAND;
}

static ssize_t storage_write_handler(struct bt_conn *conn,
                                     const struct bt_gatt_attr *attr,
                                     const void *buf,
                                     uint16_t len,
                                     uint16_t offset,
                                     uint8_t flags)
{
    if (len < 1) {
        uint8_t result_buffer[1] = {INVALID_COMMAND};
        LOG_WRN("storage write with empty payload");
        storage_notify(conn, &result_buffer, 1);
        return len;
    }

    LOG_INF("about to schedule the storage");
    LOG_INF("was sent %d  ", ((uint8_t *) buf)[0]);

    uint8_t result = parse_storage_command((void *)buf, len, conn);
    
    /* 0xFF means response was already sent */
    if (result != 0xFF) {
        uint8_t result_buffer[1] = {result};
        LOG_INF("length of storage write: %d, result: %d", len, result);
        storage_notify(conn, &result_buffer, 1);
    }
    
    return len;
}

/*
 * Batch-read buffer for BLE sync: reuse storage_buffer (4450 bytes).
 * Only need a small separate buffer for building BLE notifications.
 */
#define BLE_BATCH_PACKETS 20
static uint8_t ble_notify_buf[4 + SD_BLE_SIZE];

static void write_to_gatt(struct bt_conn *conn)
{
    int err;
    if (sync_speed_mode != SYNC_SPEED_MODE_BLE) {
        sync_speed_reset(SYNC_SPEED_MODE_BLE);
    }
    uint16_t ble_chunk = get_ble_chunk_size(conn, current_sync_file_index >= 0);
    
    if (current_sync_file_index < 0) {
        LOG_ERR("write_to_gatt called without active multi-file transfer");
        remaining_length = 0;
        return;
    }

    /* New protocol: add 4-byte timestamp prefix */
    uint32_t timestamp = (uint32_t)strtoul(sync_file_list[current_sync_file_index], NULL, 16);
        
        /* Build timestamp header once */
        ble_notify_buf[0] = (timestamp >> 24) & 0xFF;
        ble_notify_buf[1] = (timestamp >> 16) & 0xFF;
        ble_notify_buf[2] = (timestamp >> 8) & 0xFF;
        ble_notify_buf[3] = timestamp & 0xFF;

        /*
         * Multi-batch send loop: keep reading+sending until BLE TX buffers
         * saturate or we run out of data.  Previously we did ONE batch per
         * call (~4.4 KB) then returned to the main loop, which limited
         * throughput to 10-15 KB/s.  Now we keep going until -ENOMEM
         * persists, which lets BLE run at full connection-event throughput.
         */
        while (remaining_length > 0) {
            if (stop_started) {
                remaining_length = 0;
                return;
            }

            uint32_t batch_audio_size = MIN(remaining_length, (uint32_t)(ble_chunk * BLE_BATCH_PACKETS));
            if (batch_audio_size > STORAGE_BUFFER_SIZE) {
                batch_audio_size = STORAGE_BUFFER_SIZE;
            }

            int r = read_audio_data(current_read_filename, storage_buffer, batch_audio_size, current_read_offset);
            if (r <= 0) {
                LOG_ERR("Failed to read audio data: %d", r);
                remaining_length = 0;
                return;
            }
            uint32_t bytes_read = (uint32_t)r;
            uint32_t bytes_sent = 0;

            while (bytes_sent < bytes_read && remaining_length > 0) {
                if (stop_started) {
                    remaining_length = 0;
                    return;
                }

                uint32_t chunk = MIN(bytes_read - bytes_sent, ble_chunk);
                memcpy(ble_notify_buf + 4, storage_buffer + bytes_sent, chunk);

                err = storage_notify(conn, ble_notify_buf, 4 + chunk);
                if (err == -ENOMEM) {
                    if (stop_started) {
                        remaining_length = 0;
                        return;
                    }
                    k_yield();
                    continue;
                }
                if (err == -EAGAIN) {
                    return;
                }
                if (err && err != -ENOMEM) {
                    LOG_ERR("GATT notify error: %d", err);
                    return;
                }

                bytes_sent += chunk;
                sync_speed_add_bytes(chunk);
                current_read_offset += chunk;
                remaining_length -= chunk;
            }
        }
}

void storage_stop_transfer()
{
    remaining_length = 0;
    stop_started = 1;
}

bool storage_transfer_active(void)
{
    return (remaining_length > 0) || (transport_started != 0);
}

void storage_write(void)
{
    uint32_t total_sent = 0;
    uint32_t consecutive_errors = 0;

    while (1) {
        struct bt_conn *conn = get_current_connection();

        if (transport_started) {
            LOG_INF("transport started in side : %d", transport_started);
            sync_speed_mode = SYNC_SPEED_MODE_NONE;
            sync_speed_window_bytes = 0;
            sync_speed_window_start_ms = 0;
            if (current_sync_file_index < 0) {
                LOG_ERR("Transfer start requested without CMD_READ_FILE setup");
                remaining_length = 0;
            }
            transport_started = 0;  /* Clear flag after setup */
        }
        if (list_files_requested) {
            list_files_requested = 0;
            /* Always refresh cache so the response is up-to-date, then send.
             * send_file_list_response() will not re-refresh if count > 0. */
            refresh_file_list_cache();
            if (conn) {
                send_file_list_response(conn);
            }
        }
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
                storage_notify(conn, &result, 1);
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
            if (conn == NULL) {
                LOG_ERR("invalid connection");
                remaining_length = 0;
                save_offset(current_read_filename, current_read_offset);
                // save offset to flash
                continue;
                // k_yield();
            }

            write_to_gatt(conn);
            heartbeat_count = (heartbeat_count + 1) % (MAX_HEARTBEAT_FRAMES + 1);

            transport_started = 0;
            if (remaining_length == 0) {
                if (stop_started) {
                    stop_started = 0;
                } else {
                    save_offset(current_read_filename, current_read_offset);
                    LOG_INF("File done: %s", current_read_filename);

                    /* Auto-delete after successful multi-file sync. */
                    {
                        char recording_name[MAX_FILENAME_LEN] = {0};
                        get_current_filename(recording_name, sizeof(recording_name));
                        bool is_recording_file = (recording_name[0] != '\0' &&
                            strcmp(current_read_filename, recording_name) == 0);

                        if (!is_recording_file && current_read_filename[0] != '\0') {
                            LOG_INF("Auto-delete synced file: %s", current_read_filename);
                            int del_ret = delete_audio_file(current_read_filename);
                            if (del_ret < 0) {
                                LOG_ERR("Failed to auto-delete %s: %d", current_read_filename, del_ret);
                            }
                            /* Clear saved offset since deleted file is gone */
                            save_offset("", 0);
                        } else if (is_recording_file) {
                            LOG_INF("Skipping delete of active recording file: %s", current_read_filename);
                        }
                    }

                    /* BLE: notify completion */
                    LOG_PRINTK("done. attempting to download more files\n");
                    uint8_t stop_result[1] = {100};
                    (void)storage_notify(get_current_connection(), &stop_result, 1);
                    k_msleep(10);
                }
            }
        }

        // Sleep when there's no work
        if (remaining_length == 0 && !stop_started) {
            uint32_t idle_sleep_ms = get_current_connection()
                ? STORAGE_IDLE_POLL_MS_CONNECTED
                : STORAGE_IDLE_POLL_MS_OFFLINE;
            k_msleep(idle_sleep_ms);
        } else {
            k_yield();
        }
    }
}

int storage_init()
{
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
