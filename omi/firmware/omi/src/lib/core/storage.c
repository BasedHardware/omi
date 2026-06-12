#include "storage.h"

#include <errno.h>
#include <string.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>

#include "rtc.h"
#include "sd_card.h"
#include "transport.h"
#include "utils.h"

LOG_MODULE_REGISTER(storage, CONFIG_LOG_DEFAULT_LEVEL);

#define CMD_STOP_SYNC      0x03
#define CMD_RING_INFO      0x10
#define CMD_RING_READ      0x11
#define CMD_RING_ADVANCE   0x12
#define CMD_RING_CLEAR     0x13

#define STORAGE_DEFERRED 0xFF

#define INVALID_COMMAND 6
#define STORAGE_NOT_READY 9
#define SEQ_OUT_OF_RANGE 10

#define NOTIFY_ACK        0x01
#define NOTIFY_INFO       0x02
#define NOTIFY_DATA       0x03
#define NOTIFY_DONE       0x04
#define NOTIFY_READ_BEGIN 0x05

#define STORAGE_IDLE_POLL_MS_OFFLINE 2000
#define STORAGE_IDLE_POLL_MS_CONNECTED 1
#define STORAGE_WRITE_NOTIFY_ATTR_IDX 2
#define STORAGE_STATUS_REFRESH_MS 250

#define STORAGE_CHUNK_COUNT 36U
#define STORAGE_BUFFER_SIZE (RAW_AUDIO_PACKET_BYTES * STORAGE_CHUNK_COUNT)
#define STORAGE_CONTROL_NOTIFY_SIZE 32
#define STORAGE_NOTIFY_VALUE_MAX_LEN ((CONFIG_BT_L2CAP_TX_MTU > 3U) ? (CONFIG_BT_L2CAP_TX_MTU - 3U) : 20U)

#define SYNC_SPEED_LOG_INTERVAL_MS (30 * 1000)

static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t storage_write_handler(struct bt_conn *conn,
                                     const struct bt_gatt_attr *attr,
                                     const void *buf,
                                     uint16_t len,
                                     uint16_t offset,
                                     uint8_t flags);
static ssize_t storage_read_characteristic(struct bt_conn *conn,
                                           const struct bt_gatt_attr *attr,
                                           void *buf,
                                           uint16_t len,
                                           uint16_t offset);

static struct bt_uuid_128 storage_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295780, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_write_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295781, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_read_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295782, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));

K_THREAD_STACK_DEFINE(storage_stack, 4096);
static struct k_thread storage_thread;

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

static uint8_t storage_buffer[STORAGE_BUFFER_SIZE];
static uint8_t data_notify_buf[STORAGE_NOTIFY_VALUE_MAX_LEN];
static uint8_t control_notify_buf[STORAGE_CONTROL_NOTIFY_SIZE];

bool storage_is_on = false;

static uint8_t info_requested;
static uint8_t clear_requested;
static uint8_t read_request_pending;
static uint8_t advance_request_pending;
static uint8_t stop_requested;

static uint64_t pending_start_seq;
static uint32_t pending_packet_count;
static uint64_t pending_advance_seq;

static bool transfer_active;
static bool read_begin_sent;
static bool done_pending;
static uint64_t transfer_start_seq;
static uint64_t current_read_seq;
static uint32_t remaining_packets;
static uint8_t transfer_end_status;

static atomic_t storage_status_used_bytes = ATOMIC_INIT(0);
static atomic_t storage_status_unread_packets = ATOMIC_INIT(0);
static atomic_t storage_status_free_bytes = ATOMIC_INIT(0);
static atomic_t storage_status_rtc_valid = ATOMIC_INIT(0);
static int64_t storage_status_refresh_deadline_ms;

typedef enum {
    SYNC_SPEED_MODE_NONE = 0,
    SYNC_SPEED_MODE_BLE,
} sync_speed_mode_t;

static sync_speed_mode_t sync_speed_mode = SYNC_SPEED_MODE_NONE;
static int64_t sync_speed_window_start_ms;
static uint64_t sync_speed_window_bytes;

static void sync_speed_reset(sync_speed_mode_t mode)
{
    sync_speed_mode = mode;
    sync_speed_window_start_ms = k_uptime_get();
    sync_speed_window_bytes = 0;
}

static void sync_speed_add_bytes(uint32_t bytes)
{
    if (sync_speed_mode == SYNC_SPEED_MODE_NONE || bytes == 0U) {
        return;
    }

    sync_speed_window_bytes += bytes;
    int64_t now = k_uptime_get();
    int64_t elapsed_ms = now - sync_speed_window_start_ms;

    if (elapsed_ms >= SYNC_SPEED_LOG_INTERVAL_MS) {
        uint64_t kbps = (sync_speed_window_bytes * 1000U) / (elapsed_ms * 1024U);
        LOG_INF("Sync speed (BLE): %u KB/s", (uint32_t)kbps);
        sync_speed_window_start_ms = now;
        sync_speed_window_bytes = 0;
    }
}

static void storage_status_cache_set(const sd_ring_info_t *info)
{
    if (!info) {
        return;
    }

    uint64_t unread_packets = info->write_seq - info->read_seq;
    uint64_t used_bytes = unread_packets * RAW_AUDIO_PACKET_BYTES;
    uint64_t free_bytes = ((uint64_t)info->capacity_packets - unread_packets) * RAW_AUDIO_PACKET_BYTES;

    atomic_set(&storage_status_used_bytes, (atomic_val_t)MIN(used_bytes, (uint64_t)UINT32_MAX));
    atomic_set(&storage_status_unread_packets, (atomic_val_t)MIN(unread_packets, (uint64_t)UINT32_MAX));
    atomic_set(&storage_status_free_bytes, (atomic_val_t)MIN(free_bytes, (uint64_t)UINT32_MAX));
    atomic_set(&storage_status_rtc_valid, rtc_is_valid() ? 1 : 0);
}

static void storage_status_cache_refresh(void)
{
    sd_ring_info_t info;

    if (sd_ring_get_info(&info) == 0) {
        storage_status_cache_set(&info);
    }
}

static void storage_status_cache_maybe_refresh(bool force)
{
    int64_t now = k_uptime_get();

    if (!force && now < storage_status_refresh_deadline_ms) {
        return;
    }

    storage_status_refresh_deadline_ms = now + STORAGE_STATUS_REFRESH_MS;
    storage_status_cache_refresh();
}

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
    ARG_UNUSED(attr);

    storage_is_on = true;
    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_INF("Client subscribed for storage notifications");
    } else if (value == 0) {
        LOG_INF("Client unsubscribed from storage notifications");
    } else {
        LOG_ERR("Invalid storage CCC value: %u", value);
    }
}

static uint8_t storage_status_from_error(int err, uint8_t fallback_status)
{
    switch (err) {
    case -ERANGE:
        return SEQ_OUT_OF_RANGE;
    case -ETIMEDOUT:
    case -EBUSY:
    case -ECANCELED:
    case -EAGAIN:
        return STORAGE_NOT_READY;
    default:
        return fallback_status;
    }
}

static uint16_t get_ble_data_chunk_size(struct bt_conn *conn)
{
    uint16_t att_payload = 20;

    if (conn) {
        uint16_t mtu = bt_gatt_get_mtu(conn);
        if (mtu > 3U) {
            att_payload = mtu - 3U;
        }
    }

    if (att_payload <= 1U) {
        return 20;
    }

    return att_payload - 1U;
}

static int send_ack(struct bt_conn *conn, uint8_t status)
{
    control_notify_buf[0] = NOTIFY_ACK;
    control_notify_buf[1] = status;
    return storage_notify(conn, control_notify_buf, 2);
}

static int send_done(struct bt_conn *conn, uint8_t status, uint64_t next_seq)
{
    control_notify_buf[0] = NOTIFY_DONE;
    control_notify_buf[1] = status;
    sys_put_be64(next_seq, control_notify_buf + 2);
    return storage_notify(conn, control_notify_buf, 10);
}

static int send_ring_info_response(struct bt_conn *conn)
{
    sd_ring_info_t info;
    int ret = sd_ring_get_info(&info);
    if (ret < 0) {
        return send_ack(conn, storage_status_from_error(ret, STORAGE_NOT_READY));
    }

    storage_status_cache_set(&info);

    control_notify_buf[0] = NOTIFY_INFO;
    sys_put_be64(info.read_seq, control_notify_buf + 1);
    sys_put_be64(info.write_seq, control_notify_buf + 9);
    sys_put_be32(info.capacity_packets, control_notify_buf + 17);
    sys_put_be64(info.dropped_packets, control_notify_buf + 21);
    sys_put_be16(RAW_AUDIO_PACKET_BYTES, control_notify_buf + 29);
    return storage_notify(conn, control_notify_buf, 31);
}

static void reset_transfer_state(void)
{
    transfer_active = false;
    read_begin_sent = false;
    done_pending = false;
    transfer_start_seq = 0;
    current_read_seq = 0;
    remaining_packets = 0;
    transfer_end_status = 0;
}

void storage_stop_transfer(void)
{
    reset_transfer_state();
}

bool storage_transfer_active(void)
{
    return transfer_active;
}

static bool consume_stop_request(void)
{
    if (!stop_requested) {
        return false;
    }

    stop_requested = 0;
    storage_stop_transfer();
    return true;
}

static int start_pending_read(struct bt_conn *conn)
{
    sd_ring_info_t info;
    int ret = sd_ring_get_info(&info);
    if (ret < 0) {
        return send_ack(conn, storage_status_from_error(ret, STORAGE_NOT_READY));
    }

    if (pending_start_seq < info.read_seq || pending_start_seq > info.write_seq) {
        return send_ack(conn, SEQ_OUT_OF_RANGE);
    }

    storage_status_cache_set(&info);

    uint64_t available_packets = info.write_seq - pending_start_seq;
    uint32_t requested_packets = pending_packet_count;
    if (requested_packets == 0U || (uint64_t)requested_packets > available_packets) {
        requested_packets = (available_packets > UINT32_MAX) ? UINT32_MAX : (uint32_t)available_packets;
    }

    transfer_active = true;
    read_begin_sent = false;
    done_pending = false;
    transfer_start_seq = pending_start_seq;
    current_read_seq = pending_start_seq;
    remaining_packets = requested_packets;
    transfer_end_status = 0;
    sync_speed_mode = SYNC_SPEED_MODE_NONE;
    sync_speed_window_bytes = 0;
    sync_speed_window_start_ms = 0;

    return 0;
}

static void write_to_gatt(struct bt_conn *conn)
{
    if (!transfer_active || done_pending) {
        return;
    }

    if (consume_stop_request()) {
        return;
    }

    if (!read_begin_sent) {
        control_notify_buf[0] = NOTIFY_READ_BEGIN;
        sys_put_be64(transfer_start_seq, control_notify_buf + 1);
        sys_put_be32(remaining_packets, control_notify_buf + 9);

        int err = storage_notify(conn, control_notify_buf, 13);
        if (err == -ENOMEM) {
            k_yield();
            consume_stop_request();
            return;
        }
        if (err == -EAGAIN) {
            storage_stop_transfer();
            return;
        }
        if (err) {
            transfer_end_status = storage_status_from_error(err, STORAGE_NOT_READY);
            done_pending = true;
            remaining_packets = 0;
            return;
        }

        read_begin_sent = true;
    }

    if (remaining_packets == 0U) {
        done_pending = true;
        return;
    }

    if (sync_speed_mode != SYNC_SPEED_MODE_BLE) {
        sync_speed_reset(SYNC_SPEED_MODE_BLE);
    }

    uint16_t ble_chunk = get_ble_data_chunk_size(conn);

    while (remaining_packets > 0U) {
        if (consume_stop_request()) {
            return;
        }

        uint32_t packets_to_read = MIN(remaining_packets, (uint32_t)STORAGE_CHUNK_COUNT);
        uint32_t bytes_read = 0;
        uint32_t packets_read = 0;
        int ret = sd_ring_read(current_read_seq,
                               storage_buffer,
                               packets_to_read * RAW_AUDIO_PACKET_BYTES,
                               &bytes_read,
                               &packets_read);
        if (ret < 0) {
            transfer_end_status = storage_status_from_error(ret, STORAGE_NOT_READY);
            done_pending = true;
            remaining_packets = 0;
            return;
        }
        if (packets_read == 0U || bytes_read == 0U) {
            done_pending = true;
            remaining_packets = 0;
            return;
        }

        uint32_t bytes_sent = 0;
        while (bytes_sent < bytes_read) {
            if (consume_stop_request()) {
                return;
            }

            uint32_t payload = MIN(bytes_read - bytes_sent, (uint32_t)ble_chunk);
            data_notify_buf[0] = NOTIFY_DATA;
            memcpy(data_notify_buf + 1, storage_buffer + bytes_sent, payload);

            int err = storage_notify(conn, data_notify_buf, payload + 1U);
            if (err == -ENOMEM) {
                k_yield();
                if (consume_stop_request()) {
                    return;
                }
                continue;
            }
            if (err == -EAGAIN) {
                storage_stop_transfer();
                return;
            }
            if (err) {
                transfer_end_status = storage_status_from_error(err, STORAGE_NOT_READY);
                done_pending = true;
                remaining_packets = 0;
                return;
            }

            bytes_sent += payload;
            sync_speed_add_bytes(payload);
        }

        current_read_seq += packets_read;
        remaining_packets -= packets_read;
    }

    done_pending = true;
}

static ssize_t storage_read_characteristic(struct bt_conn *conn,
                                           const struct bt_gatt_attr *attr,
                                           void *buf,
                                           uint16_t len,
                                           uint16_t offset)
{
    uint32_t payload[4] = {
        (uint32_t)atomic_get(&storage_status_used_bytes),
        (uint32_t)atomic_get(&storage_status_unread_packets),
        (uint32_t)atomic_get(&storage_status_free_bytes),
        (uint32_t)atomic_get(&storage_status_rtc_valid),
    };

    return bt_gatt_attr_read(conn, attr, buf, len, offset, payload, sizeof(payload));
}

static uint8_t parse_storage_command(void *buf, uint16_t len)
{
    if (len < 1U) {
        return INVALID_COMMAND;
    }

    const uint8_t *bytes = buf;
    const uint8_t command = bytes[0];

    if (command == CMD_RING_INFO) {
        info_requested = 1;
        return STORAGE_DEFERRED;
    }

    if (command == CMD_RING_READ) {
        if (len != 9U && len != 13U) {
            return INVALID_COMMAND;
        }

        pending_start_seq = sys_get_be64(bytes + 1);
        pending_packet_count = (len == 13U) ? sys_get_be32(bytes + 9) : 0U;
        read_request_pending = 1;
        return STORAGE_DEFERRED;
    }

    if (command == CMD_RING_ADVANCE) {
        if (len != 9U) {
            return INVALID_COMMAND;
        }

        pending_advance_seq = sys_get_be64(bytes + 1);
        advance_request_pending = 1;
        return STORAGE_DEFERRED;
    }

    if (command == CMD_RING_CLEAR) {
        clear_requested = 1;
        return STORAGE_DEFERRED;
    }

    if (command == CMD_STOP_SYNC) {
        stop_requested = 1;
        return 0;
    }

    return INVALID_COMMAND;
}

static ssize_t storage_write_handler(struct bt_conn *conn,
                                     const struct bt_gatt_attr *attr,
                                     const void *buf,
                                     uint16_t len,
                                     uint16_t offset,
                                     uint8_t flags)
{
    ARG_UNUSED(attr);
    ARG_UNUSED(offset);
    ARG_UNUSED(flags);

    if (len < 1U) {
        (void)send_ack(conn, INVALID_COMMAND);
        return len;
    }

    uint8_t result = parse_storage_command((void *)buf, len);
    if (result != STORAGE_DEFERRED) {
        (void)send_ack(conn, result);
    }

    return len;
}

static void storage_write(void)
{
    while (1) {
        struct bt_conn *conn = get_current_connection();

        if (consume_stop_request()) {
            storage_status_cache_maybe_refresh(true);
        }

        if (info_requested) {
            info_requested = 0;
            if (conn) {
                (void)send_ring_info_response(conn);
            }
        }

        if (clear_requested) {
            clear_requested = 0;
            if (conn) {
                int ret = sd_ring_clear();
                if (ret >= 0) {
                    storage_status_cache_maybe_refresh(true);
                }
                (void)send_ack(conn, ret < 0 ? storage_status_from_error(ret, STORAGE_NOT_READY) : 0);
            }
        }

        if (advance_request_pending) {
            advance_request_pending = 0;
            if (conn) {
                int ret = sd_ring_advance(pending_advance_seq);
                if (ret >= 0) {
                    storage_status_cache_maybe_refresh(true);
                }
                (void)send_ack(conn, ret < 0 ? storage_status_from_error(ret, SEQ_OUT_OF_RANGE) : 0);
            }
        }

        if (read_request_pending) {
            read_request_pending = 0;
            if (conn) {
                int ret = start_pending_read(conn);
                if (ret < 0) {
                    (void)send_ack(conn, storage_status_from_error(ret, STORAGE_NOT_READY));
                }
            }
        }

        if (transfer_active) {
            if (conn == NULL) {
                storage_stop_transfer();
            } else if (done_pending) {
                int err = send_done(conn, transfer_end_status, current_read_seq);
                if (err == -ENOMEM) {
                    k_yield();
                } else if (err == -EAGAIN) {
                    reset_transfer_state();
                } else {
                    reset_transfer_state();
                }
            } else {
                write_to_gatt(conn);
            }
        }

        if (!transfer_active) {
            if (conn) {
                storage_status_cache_maybe_refresh(false);
            }
            uint32_t idle_sleep_ms = conn ? STORAGE_IDLE_POLL_MS_CONNECTED : STORAGE_IDLE_POLL_MS_OFFLINE;
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
                    (k_thread_entry_t)storage_write,
                    NULL,
                    NULL,
                    NULL,
                    K_PRIO_PREEMPT(7),
                    0,
                    K_NO_WAIT);
    return 0;
}