#include <stdint.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/ring_buffer.h>
#include <hal/nrf_power.h>
#include "transport.h"
#include "config.h"
#include "speaker.h"
#include "sdcard.h"
#include "storage.h"
#include "button.h"
#include "mic.h"
#include "accel.h"
LOG_MODULE_REGISTER(transport, CONFIG_LOG_DEFAULT_LEVEL);

// Counters for tracking function calls
extern uint32_t gatt_notify_count;
extern uint32_t write_to_tx_queue_count;

#define MAX_STORAGE_BYTES 0xFFFF0000

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
extern struct bt_gatt_service storage_service;
extern uint32_t file_num_array[2];
extern bool storage_is_on;
#endif

extern bool is_connected;

struct bt_conn *current_connection = NULL;
uint16_t current_mtu = 0;
uint16_t current_package_index = 0;
//
// Internal
//

struct k_mutex write_sdcard_mutex;

static ssize_t audio_data_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags);

static struct bt_conn_cb _callback_references;
static void audio_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t audio_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);
static ssize_t audio_codec_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);

static void dfu_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t dfu_control_point_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags);

//
// Service and Characteristic
//
// Audio service with UUID 19B10000-E8F2-537E-4F6C-D104768A1214
// exposes following characteristics:
// - Audio data (UUID 19B10001-E8F2-537E-4F6C-D104768A1214) to send audio data (read/notify)
// - Audio codec (UUID 19B10002-E8F2-537E-4F6C-D104768A1214) to send audio codec type (read)
// TODO: The current audio service UUID seems to come from old Intel sample code,
// we should change it to UUID 814b9b7c-25fd-4acd-8604-d28877beee6d
static struct bt_uuid_128 audio_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10000, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_data_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10001, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_format_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10002, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_speaker_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10003, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

static struct bt_gatt_attr audio_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&audio_service_uuid),
    BT_GATT_CHARACTERISTIC(&audio_characteristic_data_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, audio_data_read_characteristic, NULL, NULL),
    BT_GATT_CCC(audio_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&audio_characteristic_format_uuid.uuid, BT_GATT_CHRC_READ, BT_GATT_PERM_READ, audio_codec_read_characteristic, NULL, NULL),
#ifdef CONFIG_OMI_ENABLE_SPEAKER
    BT_GATT_CHARACTERISTIC(&audio_characteristic_speaker_uuid.uuid, BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_WRITE, NULL, audio_data_write_handler, NULL),
    BT_GATT_CCC(audio_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE), //
#endif

};

static struct bt_gatt_service audio_service = BT_GATT_SERVICE(audio_service_attr);

// Nordic Legacy DFU service with UUID 00001530-1212-EFDE-1523-785FEABCD123
// exposes following characteristics:
// - Control point (UUID 00001531-1212-EFDE-1523-785FEABCD123) to start the OTA update process (write/notify)
static struct bt_uuid_128 dfu_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001530, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));
static struct bt_uuid_128 dfu_control_point_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001531, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));

static struct bt_gatt_attr dfu_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&dfu_service_uuid),
    BT_GATT_CHARACTERISTIC(&dfu_control_point_uuid.uuid, BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_WRITE, NULL, dfu_control_point_write_handler, NULL),
    BT_GATT_CCC(dfu_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

static struct bt_gatt_service dfu_service = BT_GATT_SERVICE(dfu_service_attr);

// Advertisement data
static const struct bt_data bt_ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_UUID128_ALL, audio_service_uuid.val, sizeof(audio_service_uuid.val)),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

// Scan response data
static const struct bt_data bt_sd[] = {
    BT_DATA_BYTES(BT_DATA_UUID16_ALL, BT_UUID_16_ENCODE(BT_UUID_DIS_VAL)),
    BT_DATA(BT_DATA_UUID128_ALL, dfu_service_uuid.val, sizeof(dfu_service_uuid.val)),
};

//
// State and Characteristics
//

static void audio_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY)
    {
        LOG_INF("Client subscribed for notifications");
    }
    else if (value == 0)
    {
        LOG_INF("Client unsubscribed from notifications");
    }
    else
    {
        LOG_INF("Invalid CCC value: %u", value);
    }
}

static ssize_t audio_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    LOG_DBG("audio_data_read_characteristic");
    return bt_gatt_attr_read(conn, attr, buf, len, offset, NULL, 0);
}

static ssize_t audio_codec_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    uint8_t value[1] = {CODEC_ID};
    LOG_DBG("audio_codec_read_characteristic %d", CODEC_ID);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(value));
}

static ssize_t audio_data_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
    uint16_t amount = 400;
    int16_t *int16_buf = (int16_t *)buf;
    uint8_t *data = (uint8_t *)buf;
    bt_gatt_notify(conn, attr, &amount, sizeof(amount));
    amount = speak(len, buf);
    return len;
}

//
// DFU Service Handlers
//

static void dfu_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY)
    {
        LOG_INF("Client subscribed for notifications");
    }
    else if (value == 0)
    {
        LOG_INF("Client unsubscribed from notifications");
    }
    else
    {
        LOG_INF("Invalid CCC value: %u", value);
    }
}

static ssize_t dfu_control_point_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
    LOG_INF("dfu_control_point_write_handler");
    uint32_t val = 0xA8;
    if (len == 1 && ((uint8_t *)buf)[0] == 0x06)
    {
        nrf_power_gpregret_set(NRF_POWER, 0, val);
        NVIC_SystemReset();
    }
    else if (len == 2 && ((uint8_t *)buf)[0] == 0x01)
    {
        uint8_t notification_value = 0x10;
        bt_gatt_notify(conn, attr, &notification_value, sizeof(notification_value));

        nrf_power_gpregret_set(NRF_POWER, 0, val);
        NVIC_SystemReset();
    }
    return len;
}



//
// Battery Service Handlers
//

#define BATTERY_REFRESH_INTERVAL 15000 // 15 seconds

#ifdef CONFIG_OMI_ENABLE_BATTERY
void broadcast_battery_level(struct k_work *work_item);

K_WORK_DELAYABLE_DEFINE(battery_work, broadcast_battery_level);

void broadcast_battery_level(struct k_work *work_item) {
    uint16_t battery_millivolt;
    uint8_t battery_percentage;
    if (battery_get_millivolt(&battery_millivolt) == 0 &&
        battery_get_percentage(&battery_percentage, battery_millivolt) == 0) {


        LOG_PRINTK("Battery at %d mV (capacity %d%%)\n", battery_millivolt, battery_percentage);


        // Use the Zephyr BAS function to set (and notify) the battery level
        int err = bt_bas_set_battery_level(battery_percentage);
        if (err) {
            LOG_ERR("Error updating battery level: %d", err);
        }
    } else {
        LOG_ERR("Failed to read battery level");
    }

    k_work_reschedule(&battery_work, K_MSEC(BATTERY_REFRESH_INTERVAL));
}
#endif

//
// Connection Callbacks
//

static void _transport_connected(struct bt_conn *conn, uint8_t err)
{
    struct bt_conn_info info = {0};
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    storage_is_on = true;
#endif

    err = bt_conn_get_info(conn, &info);
    if (err)
    {
        LOG_ERR("Failed to get connection info (err %d)", err);
        bt_conn_unref(conn);
        return;
    }

    LOG_INF("bluetooth activated");
    current_connection = bt_conn_ref(conn);
    current_mtu = 512; // TODO: info.le.data_len->tx_max_len;

    LOG_INF("Transport connected");
    LOG_INF("current mtu %d", current_mtu);
    LOG_DBG("Interval: %d, latency: %d, timeout: %d", info.le.interval, info.le.latency, info.le.timeout);
    LOG_DBG("TX PHY %s, RX PHY %s", phy2str(info.le.phy->tx_phy), phy2str(info.le.phy->rx_phy));
    LOG_DBG("LE data len updated: TX (len: %d time: %d) RX (len: %d time: %d)", info.le.data_len->tx_max_len, info.le.data_len->tx_max_time, info.le.data_len->rx_max_len, info.le.data_len->rx_max_time);

    // TODO: recheck needed, should be the hardware issue ?
    // Request optimal connection parameters for high-throughput
    // These configs enhanced the BLE performance
    // - Updated 0: using interval max 12 helps on increasing the rps to 65
    // - Updated 1: using interval max 6 helps on increasing the rps > 100
    struct bt_le_conn_param param = {
        .interval_min = 6,    // 7.5ms (6 * 1.25ms)
        .interval_max = 6,   // 15ms (12 * 1.25ms)
        .latency = 0,         // No slave latency
        .timeout = 400,       // 4s (400 * 10ms)
    };
    err = bt_conn_le_param_update(conn, &param);
    if (err) {
        LOG_WRN("Failed to update connection parameters (err %d)", err);
    }

    // Request 2M PHY for higher throughput
    struct bt_conn_le_phy_param phy_param = {
        .options = 0,
        .pref_tx_phy = BT_GAP_LE_PHY_2M,
        .pref_rx_phy = BT_GAP_LE_PHY_2M,
    };
    bt_conn_le_phy_update(conn, &phy_param);
    // END
     
#ifdef CONFIG_OMI_ENABLE_BATTERY
    k_work_schedule(&battery_work, K_MSEC(100)); // run immediately
#endif

    is_connected = true;
}

static void _transport_disconnected(struct bt_conn *conn, uint8_t err)
{
    is_connected = false;
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    storage_is_on = false;
#endif

    LOG_INF("Transport disconnected");

    if (current_connection != NULL) {
        bt_conn_unref(current_connection);
        current_connection = NULL;
    }
    current_mtu = 0;
}

static bool _le_param_req(struct bt_conn *conn, struct bt_le_conn_param *param)
{
    LOG_INF("Transport connection parameters update request received.");
    LOG_DBG("Minimum interval: %d, Maximum interval: %d", param->interval_min, param->interval_max);
    LOG_DBG("Latency: %d, Timeout: %d", param->latency, param->timeout);

    return true;
}

static void _le_param_updated(struct bt_conn *conn, uint16_t interval,
                              uint16_t latency, uint16_t timeout)
{
    LOG_INF("Connection parameters updated.");
    LOG_DBG("[ interval: %d, latency: %d, timeout: %d ]", interval, latency, timeout);
}

static void _le_phy_updated(struct bt_conn *conn,
                            struct bt_conn_le_phy_info *param)
{
    // LOG_DBG("LE PHY updated: TX PHY %s, RX PHY %s",
    //        phy2str(param->tx_phy), phy2str(param->rx_phy));
}

static void _le_data_length_updated(struct bt_conn *conn,
                                    struct bt_conn_le_data_len_info *info)
{
    LOG_INF("LE data len updated: TX (len: %d time: %d)"
           " RX (len: %d time: %d)",
           info->tx_max_len,
           info->tx_max_time, info->rx_max_len, info->rx_max_time);
    current_mtu = info->tx_max_len;
    LOG_INF("current mtu: %d", current_mtu);
}

static struct bt_conn_cb _callback_references = {
    .connected = _transport_connected,
    .disconnected = _transport_disconnected,
    .le_param_req = _le_param_req,
    .le_param_updated = _le_param_updated,
    .le_phy_updated = _le_phy_updated,
    .le_data_len_updated = _le_data_length_updated,
};

//
// Ring Buffer
//

#define NET_BUFFER_HEADER_SIZE 3
#define RING_BUFFER_HEADER_SIZE 2
static uint8_t tx_queue[NETWORK_RING_BUF_SIZE * (CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE)];
static uint8_t tx_buffer[CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE];
static uint8_t tx_buffer_2[CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE];
static uint32_t tx_buffer_size = 0;
static struct ring_buf ring_buf;

static bool write_to_tx_queue(uint8_t *data, size_t size)
{
    // Increment the counter
    write_to_tx_queue_count++;
    
    if (size > CODEC_OUTPUT_MAX_BYTES)
    {
        return false;
    }

    // Copy data (TODO: Avoid this copy)
    tx_buffer_2[0] = size & 0xFF;
    tx_buffer_2[1] = (size >> 8) & 0xFF;
    memcpy(tx_buffer_2 + RING_BUFFER_HEADER_SIZE, data, size);

    // Write to ring buffer
    int written = ring_buf_put(&ring_buf, tx_buffer_2, (CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE)); // It always fits completely or not at all
    if (written != CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE)
    {
        return false;
    }
    else
    {
        return true;
    }
}

static bool read_from_tx_queue()
{

    // Read from ring buffer
    // memset(tx_buffer, 0, sizeof(tx_buffer));
    tx_buffer_size = ring_buf_get(&ring_buf, tx_buffer, (CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE)); // It always fits completely or not at all
    if (tx_buffer_size != (CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE))
    {
        // LOG_ERR("Failed to read from ring buffer. not enough data %d", tx_buffer_size);
        return false;
    }

    // Adjust size
    tx_buffer_size = tx_buffer[0] + (tx_buffer[1] << 8);

    return true;
}

//
// Pusher
//

// Thread
K_THREAD_STACK_DEFINE(pusher_stack, 4096);
static struct k_thread pusher_thread;
static uint16_t packet_next_index = 0;
static uint8_t pusher_temp_data[CODEC_OUTPUT_MAX_BYTES + NET_BUFFER_HEADER_SIZE];

static bool push_to_gatt(struct bt_conn *conn)
{
    // Read data from ring buffer
    if (!read_from_tx_queue())
    {
        return false;
    }

    // Push each frame
    uint8_t *buffer = tx_buffer + RING_BUFFER_HEADER_SIZE;
    uint32_t offset = 0;
    uint8_t index = 0;

    // Recombine packet
    uint32_t id = packet_next_index++;
    uint32_t packet_size = MIN(current_mtu - NET_BUFFER_HEADER_SIZE, tx_buffer_size - offset);
    //LOG_INF("push_to_gatt package size: %d, %d, %d, %d, %d", packet_size, current_mtu, NET_BUFFER_HEADER_SIZE, tx_buffer_size, offset);
    pusher_temp_data[0] = id & 0xFF;
    pusher_temp_data[1] = (id >> 8) & 0xFF;
    pusher_temp_data[2] = index;
    memcpy(pusher_temp_data + NET_BUFFER_HEADER_SIZE, buffer + offset, packet_size);

    offset += packet_size;
    index++;

    // Try send notification
    int err = bt_gatt_notify(conn, &audio_service.attrs[1], pusher_temp_data, packet_size + NET_BUFFER_HEADER_SIZE);
    // Increment the notify counter regardless of success or failure
    gatt_notify_count++;
    if (err)
    {
        LOG_ERR("bt_gatt_notify failed (err %d)", err);
        LOG_ERR("MTU: %d, packet_size: %d", current_mtu, packet_size + NET_BUFFER_HEADER_SIZE);
        return false;
    }

    return true;
}
#define OPUS_PREFIX_LENGTH 1
#define OPUS_PADDED_LENGTH 80
#define MAX_WRITE_SIZE 440
static uint32_t offset = 0;
static uint16_t buffer_offset = 0;
// bool write_to_storage(void)
// {
//     if (!read_from_tx_queue())
//     {
//         return false;
//     }

//     uint8_t *buffer = tx_buffer+2;
//     const uint32_t packet_size = tx_buffer_size;
//     //load into write at 400 bytes at a time. is faster
//     memcpy(storage_temp_data + OPUS_PREFIX_LENGTH + buffer_offset, buffer, packet_size);
//     storage_temp_data[buffer_offset] = (uint8_t)tx_buffer_size;

//     buffer_offset = buffer_offset+OPUS_PADDED_LENGTH;
//     if(buffer_offset >= OPUS_PADDED_LENGTH*5) {
//     uint8_t *write_ptr = (uint8_t*)storage_temp_data;
//     write_to_file(write_ptr,OPUS_PADDED_LENGTH*5);

//     buffer_offset = 0;
//     }

//     return true;
// }
//for improving ble bandwidth
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
static uint8_t storage_temp_data[MAX_WRITE_SIZE];
bool write_to_storage(void) {//max possible packing
    if (!read_from_tx_queue())
    {
        return false;
    }

    uint8_t *buffer = tx_buffer+2;
    uint8_t packet_size = (uint8_t)(tx_buffer_size + OPUS_PREFIX_LENGTH);

    // buffer_offset = buffer_offset+amount_to_fill;
    //check if adding the new packet will cause a overflow
    if(buffer_offset + packet_size > MAX_WRITE_SIZE-1)
    {

        storage_temp_data[buffer_offset] = tx_buffer_size;
        uint8_t *write_ptr = storage_temp_data;
        write_to_file(write_ptr,MAX_WRITE_SIZE);

        buffer_offset = packet_size;
        storage_temp_data[0] = tx_buffer_size;
        memcpy(storage_temp_data + 1, buffer, tx_buffer_size);

    }
    else if (buffer_offset + packet_size == MAX_WRITE_SIZE-1)
    {
        //exact frame needed
        storage_temp_data[buffer_offset] = tx_buffer_size;
        memcpy(storage_temp_data + buffer_offset + 1, buffer, tx_buffer_size);
        buffer_offset = 0;
        uint8_t *write_ptr = (uint8_t*)storage_temp_data;
        write_to_file(write_ptr,MAX_WRITE_SIZE);
    }
    else
    {
        storage_temp_data[buffer_offset] = tx_buffer_size;
        memcpy(storage_temp_data+ buffer_offset+1, buffer, tx_buffer_size);
        buffer_offset = buffer_offset + packet_size;
    }

    return true;
}
#endif

static bool use_storage = true;
#define MAX_FILES 10
#define MAX_AUDIO_FILE_SIZE 300000
static int recent_file_size_updated = 0;
static uint8_t heartbeat_count = 0;
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
void update_file_size()
{
    file_num_array[0] = get_file_size(1);
    file_num_array[1] = get_offset();
}
#endif

void test_pusher(void)
{
    while (1)
    {
        k_sleep(K_MSEC(1));
        uint32_t runs_count = 0;
        struct bt_conn *conn = current_connection;
        if (conn)
        {
            conn = bt_conn_ref(conn);
        }
        bool valid = true;
        if (current_mtu < MINIMAL_PACKET_SIZE)
        {
            valid = false;
        }
        else if (!conn)
        {
            valid = false;
        }
        else if (runs_count % 100 == 0)
        {
            valid = bt_gatt_is_subscribed(conn, &audio_service.attrs[1], BT_GATT_CCC_NOTIFY); // Check if subscribed
        }
        if (valid)
        {
            // Expected 100 packages per seconds
            bool sent = push_to_gatt(conn);
            if (!sent)
            {
                // k_sleep(K_MSEC(50));
            }
        }
        if (conn)
        {
            bt_conn_unref(conn);
        }
        runs_count++;
        k_yield();
    }
}

void pusher(void)
{
    k_msleep(500);
    while (1)
    {
        //
        // Load current connection
        //
        struct bt_conn *conn = current_connection;
        //updating the most recent file size is expensive!
        static bool file_size_updated = true;
        static bool connection_was_true = false;
        if (conn && !connection_was_true)
        {
            k_msleep(100);
            file_size_updated = false;
            connection_was_true = true;
        }
        else if (!conn)
        {
            connection_was_true = false;
        }
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
        if (!file_size_updated)
        {
            LOG_PRINTK("updating file size\n");
            update_file_size();

            file_size_updated = true;
        }
#endif
        if (conn)
        {
            conn = bt_conn_ref(conn);
        }
        bool valid = true;
        if (current_mtu < MINIMAL_PACKET_SIZE)
        {
            valid = false;
        }
        else if (!conn)
        {
            valid = false;
        }
        else
        {
            valid = bt_gatt_is_subscribed(conn, &audio_service.attrs[1], BT_GATT_CCC_NOTIFY); // Check if subscribed
        }

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
        if (!valid  && !storage_is_on)
        {
            bool result = false;
            if (file_num_array[1] < MAX_STORAGE_BYTES)
            {
                k_mutex_lock(&write_sdcard_mutex, K_FOREVER);
                if(is_sd_on())
                {
                    result = write_to_storage();
                }
                k_mutex_unlock(&write_sdcard_mutex);
            }
            if (result)
            {
                heartbeat_count++;
                if (heartbeat_count == 255)
                {
                    update_file_size();
                    heartbeat_count = 0;
                    LOG_PRINTK("drawing\n");
                 }
            }
            else
            {

            }
        }
#endif
        if (valid)
        {
            bool sent = push_to_gatt(conn);
            if (!sent)
            {
                // k_sleep(K_MSEC(50));
            }
        }
        if (conn)
        {
            bt_conn_unref(conn);
        }

        k_yield();
    }
}

//
// Public functions
//
int bt_off()
{
    // First disconnect any active connections
    if (current_connection != NULL) {
        bt_conn_disconnect(current_connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        bt_conn_unref(current_connection);
        current_connection = NULL;
    }

    // Stop advertising
    int err = bt_le_adv_stop();
    if (err)
    {
        LOG_ERR("Failed to stop Bluetooth advertising %d", err);
    }

    // Disable Bluetooth
    err = bt_disable();
    if (err)
    {
        LOG_ERR("Failed to disable Bluetooth %d", err);
    }

    // Turn off other peripherals
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    k_mutex_lock(&write_sdcard_mutex, K_FOREVER);
    sd_off();
    k_mutex_unlock(&write_sdcard_mutex);
#endif

    mic_off();

    // Ensure all Bluetooth resources are cleaned up
    is_connected = false;
    current_mtu = 0;

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    storage_is_on = false;
#endif

    return 0;
}

int bt_on()
{
   int err = bt_enable(NULL);
   bt_le_adv_start(BT_LE_ADV_CONN, bt_ad, ARRAY_SIZE(bt_ad), bt_sd, ARRAY_SIZE(bt_sd));
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
   bt_gatt_service_register(&storage_service);
#endif
   sd_on();
   mic_on();

   return 0;
}

//periodic advertising
int transport_start()
{
    k_mutex_init(&write_sdcard_mutex);

    // Configure callbacks
    bt_conn_cb_register(&_callback_references);

    // Enable Bluetooth
    int err = bt_enable(NULL);
    if (err)
    {
        LOG_ERR("Transport bluetooth init failed (err %d)", err);
        return err;
    }
    LOG_INF("Transport bluetooth initialized");
    //  Enable accelerometer
#ifdef CONFIG_OMI_ENABLE_ACCELEROMETER
    err = accel_start();
    if (!err)
    {
        LOG_INF("Accelerometer failed to activate\n");
    }
    else
    {
        LOG_INF("Accelerometer initialized");
        register_accel_service(current_connection);
    }
#endif
    //  Enable button
#ifdef CONFIG_OMI_ENABLE_BUTTON
    button_init();
    register_button_service();
    activate_button_work();
#endif

#ifdef CONFIG_OMI_ENABLE_SPEAKER
    err = speaker_init();
    if (err)
    {
        LOG_ERR("Speaker failed to start");
        return 0;
    }
    LOG_INF("Speaker initialized");
    register_speaker_service();

#endif

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    memset(storage_temp_data, 0, OPUS_PADDED_LENGTH * 4);
    bt_gatt_service_register(&storage_service);
#endif

    // Start advertising
    bt_gatt_service_register(&audio_service);
    bt_gatt_service_register(&dfu_service);
    err = bt_le_adv_start(BT_LE_ADV_CONN, bt_ad, ARRAY_SIZE(bt_ad), bt_sd, ARRAY_SIZE(bt_sd));
    if (err)
    {
        LOG_ERR("Transport advertising failed to start (err %d)", err);
        return err;
    }
    else
    {
        LOG_INF("Advertising successfully started");
    }

#ifdef CONFIG_OMI_ENABLE_BATTERY
    int battErr = 0;
    battErr |= battery_init();
    battErr |= battery_charge_start();
    if (battErr)
    {
        LOG_ERR("Battery init failed (err %d)", battErr);
    }
    else
    {
        LOG_INF("Battery initialized");
    }
#endif

    // Start pusher
    ring_buf_init(&ring_buf, sizeof(tx_queue), tx_queue);
    if (ring_buf_is_empty(&ring_buf)) {
        LOG_INF("Ring buffer successfully initialized");
    } else {
        LOG_ERR("Ring buffer initialization failed");
        return -1;
    }
    
    struct k_thread *thread = k_thread_create(&pusher_thread, pusher_stack, K_THREAD_STACK_SIZEOF(pusher_stack), 
                                             (k_thread_entry_t)test_pusher, NULL, NULL, NULL, 
                                             K_PRIO_PREEMPT(4), 0, K_NO_WAIT);
    if (thread == NULL) {
        LOG_ERR("Failed to create pusher thread");
        return -1;
    }
    
    LOG_INF("Pusher successfully started");

    return 0;
}

struct bt_conn *get_current_connection()
{
    return current_connection;
}

int broadcast_audio_packets(uint8_t *buffer, size_t size)
{
    if (!write_to_tx_queue(buffer, size))
    {
        return -1;
    }
    return 0;
}
