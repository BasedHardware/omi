#include "storage.h"

#include <stdio.h>
#include <string.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/atomic.h>

#include "sd_card.h"
#include "settings.h"
#include "transport.h"

LOG_MODULE_REGISTER(storage, CONFIG_LOG_DEFAULT_LEVEL);

#define SETTINGS_STORAGE_OFFSET_KEY "storage/offset"

#define MAX_PACKET_LENGTH 256
#define OPUS_ENTRY_LENGTH 80
#define FRAME_PREFIX_LENGTH 3

#define READ_COMMAND 0
#define DELETE_COMMAND 1
#define NUKE 2
#define STOP_COMMAND 3

#define INVALID_FILE_SIZE 3
#define ZERO_FILE_SIZE 4
#define INVALID_COMMAND 6

#define MAX_HEARTBEAT_FRAMES 100
#define HEARTBEAT 50
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

// File list cache
static struct audio_file_metadata file_list[MAX_AUDIO_FILES];
static uint8_t file_count = 0;

// Helper function to refresh file list
static void refresh_file_list(void)
{
    file_count = app_sd_get_file_list(file_list, MAX_AUDIO_FILES);
    LOG_INF("File list refreshed: %d files found", file_count);
}

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
    // Use cached file list (no heavy operations on BLE stack)
    if (file_count <= 0) {
        // No files available
        uint32_t empty[2] = {0, 0};
        return bt_gatt_attr_read(conn, attr, buf, len, offset, empty, sizeof(empty));
    }

    // Send file count and total size info from cache
    uint32_t total_size = 0;
    for (int i = 0; i < file_count; i++) {
        total_size += file_list[i].file_size;
    }

    // Format: [file_count, total_size, file1_size, file1_start_time_sec, file2_size, file2_start_time_sec, ...]
    // Each file gets 2 entries: size and start_offset_sec
    // Use static to avoid stack overflow
    static uint32_t response[MAX_AUDIO_FILES * 2 + 2];
    response[0] = file_count;
    response[1] = total_size;

    for (int i = 0; i < file_count && i < MAX_AUDIO_FILES; i++) {
        response[i * 2 + 2] = file_list[i].file_size;
        response[i * 2 + 3] = file_list[i].start_offset_sec;
    }

    size_t response_size = (file_count * 2 + 2) * sizeof(uint32_t);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, response, response_size);
}

uint8_t transport_started = 0;

static uint16_t packet_next_index = 0;
#define SD_BLE_SIZE 440
static uint8_t storage_write_buffer[SD_BLE_SIZE];

static uint32_t offset = 0;
static uint8_t index = 0;
static uint8_t current_packet_size = 0;
static uint8_t tx_buffer_size = 0;
static uint8_t stop_started = 0;
static uint8_t delete_started = 0;
static uint8_t current_read_num = 1;
uint32_t remaining_length = 0;

static int setup_storage_tx()
{
    transport_started = (uint8_t) 0;
    LOG_INF("about to transmit storage\n");
    k_msleep(1000);

    // Validate file number
    if (current_read_num == 0 || current_read_num > MAX_AUDIO_FILES) {
        LOG_ERR("Invalid file number: %d", current_read_num);
        transport_started = 0;
        current_read_num = 1;
        remaining_length = 0;
        return -1;
    }

    // Find file in list
    int file_idx = -1;
    for (int i = 0; i < file_count; i++) {
        if (file_list[i].file_num == current_read_num) {
            file_idx = i;
            break;
        }
    }

    if (file_idx < 0) {
        LOG_ERR("File %d not found in list", current_read_num);
        transport_started = 0;
        return -1;
    }

    remaining_length = file_list[file_idx].file_size - offset;

    LOG_INF("remaining length: %d", remaining_length);
    LOG_INF("offset: %d", offset);
    LOG_INF("file: %d (size: %d)", current_read_num, file_list[file_idx].file_size);

    return 0;
}
uint8_t delete_num = 0;
uint8_t nuke_started = 0;
static uint8_t heartbeat_count = 0;
static uint8_t parse_storage_command(void *buf, uint16_t len)
{

    if (len != 6 && len != 2) {
        LOG_INF("invalid command");
        return INVALID_COMMAND;
    }
    const uint8_t command = ((uint8_t *) buf)[0];
    const uint8_t file_num = ((uint8_t *) buf)[1];
    uint32_t size = 0;
    if (len == 6) {
        size =
            ((uint8_t *) buf)[2] << 24 | ((uint8_t *) buf)[3] << 16 | ((uint8_t *) buf)[4] << 8 | ((uint8_t *) buf)[5];
    }
    LOG_PRINTK("command successful: command: %d file: %d size: %d \n", command, file_num, size);

    if (file_num == 0 || file_num > MAX_AUDIO_FILES) {
        LOG_INF("invalid file number: %d", file_num);
        return INVALID_FILE_SIZE;
    }

    // Validate file exists in our file list
    bool file_found = false;
    for (int i = 0; i < file_count; i++) {
        if (file_list[i].file_num == file_num) {
            file_found = true;
            break;
        }
    }

    if (!file_found) {
        LOG_INF("file %d not found in list", file_num);
        return INVALID_FILE_SIZE;
    }
    if (command == READ_COMMAND) // read
    {
        // Find the file in our list
        int file_idx = -1;
        for (int i = 0; i < file_count; i++) {
            if (file_list[i].file_num == file_num) {
                file_idx = i;
                break;
            }
        }

        if (file_idx < 0) {
            LOG_ERR("File %d not in list", file_num);
            return INVALID_FILE_SIZE;
        }

        uint32_t file_size = file_list[file_idx].file_size;

        if (file_size == 0) {
            LOG_INF("file size is 0");
            return ZERO_FILE_SIZE;
        } else if (size > file_size) {
            LOG_INF("requested size %d is too large for file size %d", size, file_size);
            return 5;
        } else {
            LOG_INF("valid command, setting up file %d at offset %d", file_num, size);
            offset = size - (size % SD_BLE_SIZE);
            current_read_num = file_num;
            transport_started = 1;
        }
    } else if (command == DELETE_COMMAND) {
        delete_num = file_num;
        delete_started = 1;
    } else if (command == NUKE) {
        nuke_started = 1;
    } else if (command == STOP_COMMAND) // should be no explicit stop command, send heartbeats to keep connection alive
    {
        remaining_length = 0;
        stop_started = 1;
    } else if (command == HEARTBEAT) {
        heartbeat_count = 0;
    } else {
        LOG_INF("invalid command \n");
        return 6;
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

    uint8_t result_buffer[1] = {0};
    uint8_t result = parse_storage_command(buf, len);
    result_buffer[0] = result;
    LOG_INF("length of storage write: %d", len);
    LOG_INF("result: %d ", result);
    bt_gatt_notify(conn, &storage_service.attrs[1], &result_buffer, 1);
    k_msleep(500);
    return len;
}

// static void write_to_gatt(struct bt_conn *conn)
// {
//     uint32_t id = packet_next_index++;
//     index = 0;
//     storage_write_buffer[0] = id & 0xFF;
//     storage_write_buffer[1] = (id >> 8) & 0xFF;
//     storage_write_buffer[2] = index;

//     const uint32_t packet_size = MIN(remaining_length,OPUS_ENTRY_LENGTH);

//     int r = read_audio_data(storage_write_buffer+FRAME_PREFIX_LENGTH,packet_size,offset);
//     offset = offset + packet_size;

//     index++;

//     int err = bt_gatt_notify(conn, &storage_service.attrs[1], &storage_write_buffer,packet_size+FRAME_PREFIX_LENGTH);
//     if (err)
//     {
//         LOG_PRINTK("error writing to gatt: %d\n",err);
//     }
//     else
//     {
//     remaining_length = remaining_length - OPUS_ENTRY_LENGTH;
//     }
// }

static void write_to_gatt(struct bt_conn *conn)
{
    uint32_t packet_size = MIN(remaining_length, SD_BLE_SIZE);

    int r = app_sd_read_audio(current_read_num, storage_write_buffer, packet_size, offset);
    if (r < 0) {
        LOG_ERR("Failed to read from SD card: %d", r);
        remaining_length = 0;
        return;
    }

    offset = offset + packet_size;
    int err = bt_gatt_notify(conn, &storage_service.attrs[1], &storage_write_buffer, packet_size);
    if (err) {
        LOG_PRINTK("error writing to gatt: %d\n", err);
    } else {
        remaining_length = remaining_length - packet_size;
    }
}

void storage_write(void)
{
    uint32_t idle_count = 0;
    while (1) {
        struct bt_conn *conn = get_current_connection();

        if (transport_started) {
            LOG_INF("transpor started in side : %d", transport_started);
            setup_storage_tx();
        }
        // probably prefer to implement using work orders for delete,nuke,etc...
        if (delete_started) {
            LOG_INF("delete:%d\n", delete_num);
            int err = app_sd_delete_file(delete_num);
            offset = 0;

            if (err) {
                LOG_PRINTK("error deleting file\n");
            } else {
                uint8_t result_buffer[1] = {200};
                if (conn) {
                    bt_gatt_notify(get_current_connection(), &storage_service.attrs[1], &result_buffer, 1);
                }
                // Refresh file list after delete
                refresh_file_list();
            }
            delete_started = 0;
            k_msleep(10);
        }
        if (nuke_started) {
            app_sd_delete_all_files();
            offset = 0;
            nuke_started = 0;
            // Refresh file list after nuke
            refresh_file_list();
        }
        if (stop_started) {
            remaining_length = 0;
            stop_started = 0;
            // Note: offset is now per-file, saved in app_sd metadata
        }
        if (heartbeat_count == MAX_HEARTBEAT_FRAMES) {
            LOG_PRINTK("no heartbeat sent\n");
            // Note: offset tracking is now handled by app_sd
            // k_yield();
            // continue;
        }

        if (remaining_length > 0) {
            if (conn == NULL) {
                LOG_ERR("invalid connection");
                remaining_length = 0;
                app_settings_save_storage_offset(offset);
                continue;
                // k_yield();
            }
            // LOG_PRINTK("remaining length: %d\n",remaining_length);

            write_to_gatt(conn);
            heartbeat_count = (heartbeat_count + 1) % (MAX_HEARTBEAT_FRAMES + 1);

            transport_started = 0;
            if (remaining_length == 0) {
                if (stop_started) {
                    stop_started = 0;
                } else {
                    LOG_PRINTK("file %d transfer complete\n", current_read_num);
                    uint8_t stop_result[1] = {100};
                    int err = bt_gatt_notify(get_current_connection(), &storage_service.attrs[1], &stop_result, 1);
                    k_sleep(K_MSEC(10));
                    offset = 0; // Reset offset for next file
                }
            }
        } else {
            // Idle - periodically refresh file list (every ~60 seconds of idle time)
            idle_count++;
            if (idle_count >= 60000) {
                refresh_file_list();
                idle_count = 0;
            }
        }
        k_yield();
    }
}

int storage_init()
{
    // Load saved offset from settings
    app_settings_load_storage_offset(&offset);

    // Initialize file list cache
    LOG_INF("Initializing storage file list...");
    refresh_file_list();

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
