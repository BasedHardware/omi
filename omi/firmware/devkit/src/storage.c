#include "storage.h"

#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>

#include "sdcard.h"
#include "transport.h"
#include "utils.h"

LOG_MODULE_REGISTER(storage, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_PACKET_LENGTH 256
#define OPUS_ENTRY_LENGTH 80
#define FRAME_PREFIX_LENGTH 3

#define STORAGE_STATUS_OK 0x00
#define STORAGE_STATUS_DOWNLOAD_COMPLETE 0x64
#define STORAGE_STATUS_DELETE_COMPLETE 0xC8
#define STORAGE_STATUS_CHUNK_STREAM_BEGIN 0x70
#define STORAGE_STATUS_CHUNK_STREAM_COMPLETE 0x71
#define STORAGE_STATUS_CHUNK_STREAM_ERROR 0x72

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
static struct bt_uuid_128 storage_chunk_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295783, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_chunk_send_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295784, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_chunk_delete_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295785, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static ssize_t storage_read_characteristic(struct bt_conn *conn,
                                           const struct bt_gatt_attr *attr,
                                           void *buf,
                                           uint16_t len,
                                           uint16_t offset);
static ssize_t storage_chunk_characteristic(struct bt_conn *conn,
                                            const struct bt_gatt_attr *attr,
                                            void *buf,
                                            uint16_t len,
                                            uint16_t offset);
static void storage_chunk_ccc_cfg_changed(const struct bt_gatt_attr *attr,
                                          uint16_t value);
static ssize_t storage_chunk_send_write(struct bt_conn *conn,
                                        const struct bt_gatt_attr *attr,
                                        const void *buf,
                                        uint16_t len,
                                        uint16_t attr_offset,
                                        uint8_t flags);
static ssize_t storage_chunk_delete_write(struct bt_conn *conn,
                                          const struct bt_gatt_attr *attr,
                                          const void *buf,
                                          uint16_t len,
                                          uint16_t attr_offset,
                                          uint8_t flags);

#define STORAGE_ATTR_CHUNK_VALUE_INDEX 8  // Index of storage_chunk characteristic (READ+NOTIFY)

static atomic_t chunk_send_pending = ATOMIC_INIT(0);
static atomic_t chunk_delete_pending = ATOMIC_INIT(0);
static atomic_t pending_chunk_send_id = ATOMIC_INIT(0);
static atomic_t pending_chunk_delete_id = ATOMIC_INIT(0);

K_THREAD_STACK_DEFINE(storage_stack, 4096);
static struct k_thread storage_thread;

extern uint8_t file_count;
extern uint32_t file_num_array[2];
extern bool chunking_enabled;
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
    BT_GATT_CHARACTERISTIC(&storage_chunk_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ,
                           storage_chunk_characteristic,
                           NULL,
                           NULL),
    BT_GATT_CCC(storage_chunk_ccc_cfg_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&storage_chunk_send_uuid.uuid,
                           BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_WRITE,
                           NULL,
                           storage_chunk_send_write,
                           NULL),
    BT_GATT_CHARACTERISTIC(&storage_chunk_delete_uuid.uuid,
                           BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_WRITE,
                           NULL,
                           storage_chunk_delete_write,
                           NULL),

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

static void storage_chunk_ccc_cfg_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
    ARG_UNUSED(attr);

    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_DBG("Chunk counter notifications enabled");
    } else {
        LOG_DBG("Chunk counter notifications disabled");
    }
}

static ssize_t storage_chunk_characteristic(struct bt_conn *conn,
                                            const struct bt_gatt_attr *attr,
                                            void *buf,
                                            uint16_t len,
                                            uint16_t offset)
{
    uint32_t counters[2] = {0};
    get_chunk_counter_snapshot(&counters[0], &counters[1]);

    return bt_gatt_attr_read(conn, attr, buf, len, offset, counters, sizeof(counters));
}

static ssize_t storage_chunk_send_write(struct bt_conn *conn,
                                        const struct bt_gatt_attr *attr,
                                        const void *buf,
                                        uint16_t len,
                                        uint16_t attr_offset,
                                        uint8_t flags)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(attr_offset);
    ARG_UNUSED(flags);

    if (!chunking_enabled) {
        LOG_WRN("chunk send ignored, chunking disabled");
        return BT_GATT_ERR(BT_ATT_ERR_WRITE_NOT_PERMITTED);
    }

    if (len != sizeof(uint32_t)) {
        LOG_WRN("chunk send invalid len %u", len);
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    uint32_t chunk_id = sys_get_le32(buf);
    if (chunk_id == 0U) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_PDU);
    }

    // Validate chunk_id is within valid range
    uint32_t start_counter = 0;
    uint32_t current_counter = 0;
    get_chunk_counter_snapshot(&start_counter, &current_counter);

    if (start_counter == 0 && current_counter == 0) {
        LOG_WRN("Chunk send rejected: no chunks exist (id=%u)", chunk_id);
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    if (chunk_id < start_counter || chunk_id > current_counter) {
        LOG_WRN("Chunk send rejected: id=%u out of range [%u, %u]", 
                chunk_id, start_counter, current_counter);
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    LOG_DBG("Chunk send request received (id=%u)", chunk_id);

    atomic_set(&pending_chunk_send_id, (int)chunk_id);
    atomic_set(&chunk_send_pending, 1);

    return len;
}

static ssize_t storage_chunk_delete_write(struct bt_conn *conn,
                                          const struct bt_gatt_attr *attr,
                                          const void *buf,
                                          uint16_t len,
                                          uint16_t attr_offset,
                                          uint8_t flags)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(attr_offset);
    ARG_UNUSED(flags);

    if (!chunking_enabled) {
        LOG_WRN("chunk delete ignored, chunking disabled");
        return BT_GATT_ERR(BT_ATT_ERR_WRITE_NOT_PERMITTED);
    }

    if (len != sizeof(uint32_t)) {
        LOG_WRN("chunk delete invalid len %u", len);
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    uint32_t chunk_id = sys_get_le32(buf);
    if (chunk_id == 0U) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_PDU);
    }

    // Validate chunk_id is within valid range
    uint32_t start_counter = 0;
    uint32_t current_counter = 0;
    get_chunk_counter_snapshot(&start_counter, &current_counter);

    if (start_counter == 0 && current_counter == 0) {
        LOG_WRN("Chunk delete rejected: no chunks exist (id=%u)", chunk_id);
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    if (chunk_id < start_counter || chunk_id > current_counter) {
        LOG_WRN("Chunk delete rejected: id=%u out of range [%u, %u]", 
                chunk_id, start_counter, current_counter);
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    LOG_DBG("Chunk delete request received (id=%u)", chunk_id);

    atomic_set(&pending_chunk_delete_id, (int)chunk_id);
    atomic_set(&chunk_delete_pending, 1);

    return len;
}

static ssize_t storage_read_characteristic(struct bt_conn *conn,
                                           const struct bt_gatt_attr *attr,
                                           void *buf,
                                           uint16_t len,
                                           uint16_t offset)
{
    k_msleep(10);
    uint32_t amount[2] = {0};
    for (int i = 0; i < 2; i++) {
        amount[i] = file_num_array[i];
    }
    ssize_t result = bt_gatt_attr_read(conn, attr, buf, len, offset, amount, 2 * sizeof(uint32_t));
    return result;
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

static uint32_t chunk_stream_offset = 0;
static uint32_t chunk_stream_remaining = 0;
static uint32_t chunk_stream_total = 0;
static uint32_t chunk_stream_id = 0;

static void storage_notify_chunk_begin(uint32_t chunk_id, uint32_t total_len)
{
    struct bt_conn *conn = get_current_connection();
    if (!conn) {
        return;
    }

    uint8_t frame[9];
    frame[0] = STORAGE_STATUS_CHUNK_STREAM_BEGIN;
    sys_put_le32(chunk_id, &frame[1]);
    sys_put_le32(total_len, &frame[5]);
    bt_gatt_notify(conn, &storage_service.attrs[1], frame, sizeof(frame));
}

static void storage_notify_chunk_complete(uint32_t chunk_id, uint32_t total_len)
{
    struct bt_conn *conn = get_current_connection();
    if (!conn) {
        return;
    }

    uint8_t frame[9];
    frame[0] = STORAGE_STATUS_CHUNK_STREAM_COMPLETE;
    sys_put_le32(chunk_id, &frame[1]);
    sys_put_le32(total_len, &frame[5]);
    bt_gatt_notify(conn, &storage_service.attrs[1], frame, sizeof(frame));
}

static void storage_notify_chunk_error(uint32_t chunk_id, uint32_t offset, uint8_t err)
{
    struct bt_conn *conn = get_current_connection();
    if (!conn) {
        return;
    }

    uint8_t frame[10];
    frame[0] = STORAGE_STATUS_CHUNK_STREAM_ERROR;
    sys_put_le32(chunk_id, &frame[1]);
    sys_put_le32(offset, &frame[5]);
    frame[9] = err;
    bt_gatt_notify(conn, &storage_service.attrs[1], frame, sizeof(frame));
}

static void reset_chunk_stream_state(void)
{
    chunk_stream_offset = 0;
    chunk_stream_remaining = 0;
    chunk_stream_total = 0;
    chunk_stream_id = 0;
}

static bool prepare_chunk_stream(uint32_t chunk_id)
{
    uint32_t file_size = 0;
    int err = stream_chunk_file(chunk_id, &file_size);
    if (err) {
        LOG_ERR("stream_chunk_file failed for %u: %d", chunk_id, err);
        reset_chunk_stream_state();
        storage_notify_chunk_error(chunk_id, 0U, (uint8_t)err);
        return false;
    }
    LOG_DBG("Chunk %u streaming prepared (size=%u bytes)", chunk_id, file_size);
    chunk_stream_offset = 0;
    chunk_stream_remaining = file_size;
    chunk_stream_total = file_size;
    chunk_stream_id = chunk_id;
    storage_notify_chunk_begin(chunk_id, chunk_stream_total);
    return true;
}

bool chunk_stream_active(void)
{
    return chunk_stream_remaining > 0;
}

uint32_t chunk_stream_take(uint8_t *buffer, uint32_t max_len)
{
    uint32_t to_read = MIN(chunk_stream_remaining, max_len);
    if (to_read == 0) {
        return 0;
    }

    int rc = read_audio_data(buffer, to_read, chunk_stream_offset);
    if (rc <= 0) {
        LOG_ERR("Failed to read chunk data: %d", rc);
        uint8_t err_code = (rc < 0) ? (uint8_t)(-rc) : 0xEE;
        storage_notify_chunk_error(chunk_stream_id, chunk_stream_offset, err_code);
        reset_chunk_stream_state();
        return 0;
    }

    chunk_stream_offset += (uint32_t)rc;
    chunk_stream_remaining -= (uint32_t)rc;
    LOG_DBG("Chunk stream read %u bytes (offset=%u remaining=%u)",
            (uint32_t)rc,
            chunk_stream_offset,
            chunk_stream_remaining);
    return (uint32_t)rc;
}

static void handle_chunk_requests(struct bt_conn *conn)
{
    if (atomic_cas(&chunk_delete_pending, 1, 0)) {
        uint32_t delete_id = (uint32_t)atomic_get(&pending_chunk_delete_id);
        LOG_DBG("Processing chunk delete request (id=%u)", delete_id);
        int err = delete_chunk_file(delete_id);
        if (err) {
            LOG_ERR("delete_chunk_file failed for %u: %d", delete_id, err);
        } else {
            uint32_t counters[2] = {0};
            get_chunk_counter_snapshot(&counters[0], &counters[1]);
            LOG_INF("Chunk %u deleted successfully (start=%u current=%u)",
                    delete_id,
                    counters[0],
                    counters[1]);
            bt_gatt_notify(conn,
                        &storage_service.attrs[STORAGE_ATTR_CHUNK_VALUE_INDEX],
                        counters,
                        sizeof(counters));
        }
    }

    if (atomic_cas(&chunk_send_pending, 1, 0)) {
        uint32_t send_id = (uint32_t)atomic_get(&pending_chunk_send_id);
        if (prepare_chunk_stream(send_id)) {
            LOG_DBG("Chunk %u ready for streaming", send_id);
        }
    }
}

static void stream_chunk_if_ready(struct bt_conn *conn)
{
    if (!chunk_stream_active() || conn == NULL) {
        return;
    }

    uint32_t bytes = chunk_stream_take(storage_write_buffer, SD_BLE_SIZE);
    if (bytes == 0) {
        return;
    }

    int err = bt_gatt_notify(conn, &storage_service.attrs[1], storage_write_buffer, bytes);
    if (err) {
        LOG_ERR("Failed to notify chunk data: %d", err);
        storage_notify_chunk_error(chunk_stream_id, chunk_stream_offset, (uint8_t)err);
        reset_chunk_stream_state();
        return;
    }

    LOG_DBG("Notified %u bytes of chunk data", bytes);

    if (!chunk_stream_active()) {
        LOG_DBG("Chunk stream complete");
        storage_notify_chunk_complete(chunk_stream_id, chunk_stream_total);
        reset_chunk_stream_state();
    }
}


static int setup_storage_tx()
{
    transport_started = (uint8_t) 0;
    // offset = 0;
    LOG_INF("about to transmit storage\n");
    k_msleep(1000);
    int res = move_read_pointer(current_read_num);
    if (res) {
        LOG_INF("bad pointer");
        transport_started = 0;
        current_read_num = 1;
        remaining_length = 0;
        return -1;
    }

    LOG_INF("current read ptr %d", current_read_num);

    remaining_length = file_num_array[current_read_num - 1];
    if (current_read_num == file_count) {
        remaining_length = get_file_size(file_count);
    }

    remaining_length = remaining_length - offset;

    // offset=offset_;
    LOG_INF("remaining length: %d", remaining_length);
    LOG_INF("offset: %d", offset);
    LOG_INF("file: %d", current_read_num);

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

    if (file_num == 0) {
        LOG_INF("invalid file count 0");
        return INVALID_FILE_SIZE;
    }
    if (file_num > file_count) // invalid file count
    {
        LOG_INF("invalid file count");
        return INVALID_FILE_SIZE;
        // add audio all?
    }
    if (command == READ_COMMAND) // read
    {
        uint32_t temp = file_num_array[file_num - 1];
        if (file_num == (file_count)) {
            LOG_INF("file_count == final file");
            offset = size - (size % SD_BLE_SIZE); // round down to nearest SD_BLE_SIZE
            current_read_num = file_num;
            transport_started = 1;
        } else if (temp == 0) {
            LOG_INF("file size is 0");
            return ZERO_FILE_SIZE;
        } else if (size > temp) {
            LOG_INF("requested size is too large");
            return 5;
        } else {
            LOG_INF("valid command, setting up ");
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
{ // unsafe. designed for max speeds. udp?

    uint32_t packet_size = MIN(remaining_length, SD_BLE_SIZE);

    int r = read_audio_data(storage_write_buffer, packet_size, offset);
    offset = offset + packet_size;
    int err = bt_gatt_notify(conn, &storage_service.attrs[1], &storage_write_buffer, packet_size);
    if (err) {
        LOG_PRINTK("error writing to gatt: %d\n", err);
    } else {
        remaining_length = remaining_length - SD_BLE_SIZE;
    }
    // LOG_PRINTK("wrote to gatt %d\n",err);
}

void storage_write(void)
{
    while (1) {
        struct bt_conn *conn = get_current_connection();

        // Only process chunk operations if chunking is enabled
        if (chunking_enabled) {
            handle_chunk_requests(conn);
            stream_chunk_if_ready(conn);
        }

        if (transport_started) {
            LOG_INF("transpor started in side : %d", transport_started);
            setup_storage_tx();
        }
        // probably prefer to implement using work orders for delete,nuke,etc...
        if (delete_started) {
            LOG_INF("delete:%d\n", delete_started);
            int err = clear_audio_file(1);
            offset = 0;
            save_offset(offset);

            if (err) {
                LOG_PRINTK("error clearing\n");
            } else {
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
            save_offset(0);
            nuke_started = 0;
        }
        if (stop_started) {
            remaining_length = 0;
            stop_started = 0;
            save_offset(offset);
        }
        if (heartbeat_count == MAX_HEARTBEAT_FRAMES) {
            LOG_PRINTK("no heartbeat sent\n");
            save_offset(offset);
            // k_yield();
            // continue;
        }

        if (remaining_length > 0) {
            if (conn == NULL) {
                LOG_ERR("invalid connection");
                remaining_length = 0;
                save_offset(offset);
                // save offset to flash
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
                    LOG_PRINTK("done. attempting to download more files\n");
                    uint8_t stop_result[1] = {100};
                    int err = bt_gatt_notify(get_current_connection(), &storage_service.attrs[1], &stop_result, 1);
                    k_sleep(K_MSEC(10));
                }
            }
        }
        k_yield();
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
