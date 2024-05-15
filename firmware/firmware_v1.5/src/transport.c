#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/ring_buffer.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/sys/atomic.h>
#include "transport.h"
#include "config.h"
#include "utils.h"

//
// Internal
//

static uint8_t battery_level = 100U;
static bool battery_charging = false;
static bool is_allowed = false;
static uint16_t connected = 0;
static struct transport_cb *external_callbacks = NULL;
static struct bt_conn_cb _callback_references;
static ssize_t audio_characteristic_read(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);
static ssize_t audio_characteristic_format_read(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);
static ssize_t audio_characteristic_allowed_read(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);
static ssize_t battery_characteristic_read(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);
static void ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static void battery_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static void mute_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);

//
// Audio Service
//

static struct bt_uuid_128 audio_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10000, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10001, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_format_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10002, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_allow_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10003, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_battery = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10004, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_gatt_attr audio_attrs[] = {
    BT_GATT_PRIMARY_SERVICE(&audio_service_uuid),
    // Streaming
    BT_GATT_CHARACTERISTIC(&audio_characteristic_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, audio_characteristic_read, NULL, NULL),
    BT_GATT_CCC(ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    // Format
    BT_GATT_CHARACTERISTIC(&audio_characteristic_format_uuid.uuid, BT_GATT_CHRC_READ, BT_GATT_PERM_READ, audio_characteristic_format_read, NULL, NULL),
    // Mute
    BT_GATT_CHARACTERISTIC(&audio_characteristic_allow_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, audio_characteristic_allowed_read, NULL, NULL),
    BT_GATT_CCC(mute_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE)};
static struct bt_gatt_service audio_service = BT_GATT_SERVICE(audio_attrs);

//
// Battery Service
//

static const struct bt_gatt_cpf level_cpf = {
    .format = 0x04, /* uint8 */
    .exponent = 0x0,
    .unit = 0x27AD,        /* Percentage */
    .name_space = 0x01,    /* Bluetooth SIG */
    .description = 0x0106, /* "main" */
};

static struct bt_gatt_attr bas_attrs[] = {
    BT_GATT_PRIMARY_SERVICE(BT_UUID_BAS),
    BT_GATT_CHARACTERISTIC(BT_UUID_BAS_BATTERY_LEVEL,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ, battery_characteristic_read, NULL,
                           &battery_level),
    BT_GATT_CCC(battery_ccc_config_changed_handler,
                BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CPF(&level_cpf),
};
static struct bt_gatt_service bas_service = BT_GATT_SERVICE(bas_attrs);

//
// Advertisement data
//

static const struct bt_data bt_ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

//
// Scan response data
//

static const struct bt_data bt_sd[] = {
    BT_DATA(BT_DATA_UUID128_ALL, audio_service_uuid.val, sizeof(audio_service_uuid.val)),
};

//
// State and Characteristics
//

struct bt_conn *current_connection = NULL;
uint16_t current_mtu = 0;
uint16_t current_package_index = 0;

static ssize_t audio_characteristic_read(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    printk("audio_characteristic_read\n");
    return bt_gatt_attr_read(conn, attr, buf, len, offset, NULL, 0);
}

static ssize_t audio_characteristic_format_read(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    printk("audio_characteristic_format_read\n");
    uint8_t value[1] = {CODEC_ID};
    return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(value));
}

static ssize_t audio_characteristic_allowed_read(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    printk("audio_characteristic_allowed_read\n");
    uint8_t value[1] = {(is_allowed ? 1 : 0)};
    return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(value));
}

static ssize_t battery_characteristic_read(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    printk("battery_characteristic_read\n");
    uint8_t value[1] = {battery_level};
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &value, sizeof(value));
}

static void ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY)
    {
        printk("Client subscribed for audio stream\n");
        connected += 1;
        if (connected == 1 && external_callbacks && external_callbacks->subscribed)
        {
            external_callbacks->subscribed();
        }
    }
    else if (value == 0)
    {
        printk("Client unsubscribed from audio stream\n");
        connected -= 1;
        if (connected == 0 && external_callbacks && external_callbacks->unsubscribed)
        {
            external_callbacks->unsubscribed();
        }
    }
    else
    {
        printk("Invalid CCC value: %u\n", value);
    }
}

static void battery_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY)
    {
        printk("Client subscribed for battery updates\n");
    }
    else if (value == 0)
    {
        printk("Client unsubscribed from battery updates\n");
    }
    else
    {
        printk("Invalid CCC value: %u\n", value);
    }
}

static void mute_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY)
    {
        printk("Client subscribed for mute updates\n");
    }
    else if (value == 0)
    {
        printk("Client unsubscribed from mute updates\n");
    }
    else
    {
        printk("Invalid CCC value: %u\n", value);
    }
}

//
// Connection Callbacks
//

static const char *phy2str(uint8_t phy)
{
    switch (phy)
    {
    case 0:
        return "No packets";
    case BT_GAP_LE_PHY_1M:
        return "LE 1M";
    case BT_GAP_LE_PHY_2M:
        return "LE 2M";
    case BT_GAP_LE_PHY_CODED:
        return "LE Coded";
    default:
        return "Unknown";
    }
}

static void _transport_connected(struct bt_conn *conn, uint8_t err)
{
    struct bt_conn_info info = {0};
    err = bt_conn_get_info(conn, &info);
    if (err)
    {
        printk("Failed to get connection info (err %d)\n", err);
        return;
    }

    // Configure preferences
    struct bt_conn_le_phy_param phy_param;
    phy_param.options = BT_CONN_LE_PHY_OPT_NONE;
    phy_param.pref_tx_phy = BT_GAP_LE_PHY_2M;
    phy_param.pref_rx_phy = BT_GAP_LE_PHY_1M;
    err = bt_conn_le_phy_update(conn, &phy_param);
    if (err)
    {
        printk("PHY update request failed (err %d)\n", err);
        return;
    }

    // Disconnect existing connection
    if (current_connection)
    {
        if (bt_conn_disconnect(current_connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN)) {
            printk("Failed to disconnect existing connection\n");
        }
        bt_conn_unref(current_connection);
        current_connection = NULL;
        current_mtu = 0;
    }

    // Save connection
    current_connection = bt_conn_ref(conn);
    current_mtu = info.le.data_len->tx_max_len;
    printk("Connected\n");
    printk("Interval: %d, latency: %d, timeout: %d\n", info.le.interval, info.le.latency, info.le.timeout);
    printk("TX PHY %s, RX PHY %s\n", phy2str(info.le.phy->tx_phy), phy2str(info.le.phy->rx_phy));
    printk("LE data len updated: TX (len: %d time: %d) RX (len: %d time: %d)\n", info.le.data_len->tx_max_len, info.le.data_len->tx_max_time, info.le.data_len->rx_max_len, info.le.data_len->rx_max_time);
}

static void _transport_disconnected(struct bt_conn *conn, uint8_t err)
{
    printk("Disconnected\n");
    bt_conn_unref(conn);
    current_connection = NULL;
    current_mtu = 0;
}

static bool _le_param_req(struct bt_conn *conn, struct bt_le_conn_param *param)
{
    printk("Connection parameters update request received.\n");
    printk("Minimum interval: %d, Maximum interval: %d\n",
           param->interval_min, param->interval_max);
    printk("Latency: %d, Timeout: %d\n", param->latency, param->timeout);

    return false;
}

static void _le_param_updated(struct bt_conn *conn, uint16_t interval,
                              uint16_t latency, uint16_t timeout)
{
    printk("Connection parameters updated.\n"
           " interval: %d, latency: %d, timeout: %d\n",
           interval, latency, timeout);
}

static void _le_phy_updated(struct bt_conn *conn,
                            struct bt_conn_le_phy_info *param)
{
    printk("LE PHY updated: TX PHY %s, RX PHY %s\n",
           phy2str(param->tx_phy), phy2str(param->rx_phy));
}

static void _le_data_length_updated(struct bt_conn *conn,
                                    struct bt_conn_le_data_len_info *info)
{
    printk("LE data len updated: TX (len: %d time: %d)"
           " RX (len: %d time: %d)\n",
           info->tx_max_len,
           info->tx_max_time, info->rx_max_len, info->rx_max_time);
    current_mtu = info->tx_max_len;
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
        // printk("Failed to read from ring buffer %d\n", tx_buffer_size);
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
K_THREAD_STACK_DEFINE(pusher_stack, 1024);
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
    while (offset < tx_buffer_size)
    {
        // Recombine packet
        uint32_t id = packet_next_index++;
        uint32_t packet_size = MIN(current_mtu - NET_BUFFER_HEADER_SIZE, tx_buffer_size - offset);
        pusher_temp_data[0] = id & 0xFF;
        pusher_temp_data[1] = (id >> 8) & 0xFF;
        pusher_temp_data[2] = index;
        memcpy(pusher_temp_data + NET_BUFFER_HEADER_SIZE, buffer + offset, packet_size);
        offset += packet_size;
        index++;

        while (true)
        {

            // Try send notification
            int err = bt_gatt_notify(conn, &audio_service.attrs[1], pusher_temp_data, packet_size + NET_BUFFER_HEADER_SIZE);

            // Log failure
            if (err)
            {
                printk("bt_gatt_notify failed (err %d)\n", err);
                printk("MTU: %d, packet_size: %d\n", current_mtu, packet_size + NET_BUFFER_HEADER_SIZE);
                k_sleep(K_MSEC(1));
            }

            // Try to send more data if possible
            if (err == -EAGAIN || err == -ENOMEM)
            {
                continue;
            }

            // Break if success
            break;
        }
    }

    return true;
}

void pusher(void)
{
    while (1)
    {

        //
        // Load current connection
        //

        struct bt_conn *conn = current_connection;
        bool use_gatt = true;
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

        // If no valid mode exists - discard whole buffer
        if (!valid)
        {
            ring_buf_reset(&ring_buf);
            k_sleep(K_MSEC(10));
        }

        // Handle GATT
        if (use_gatt && valid)
        {
            bool sent = push_to_gatt(conn);
            if (!sent)
            {
                k_sleep(K_MSEC(50));
            }
        }

        if (conn)
        {
            bt_conn_unref(conn);
        }
    }
}

//
// Public functions
//

int transport_start()
{

    // Configure callbacks
    bt_conn_cb_register(&_callback_references);

    // Enable Bluetooth
    int err = bt_enable(NULL);
    if (err)
    {
        printk("Bluetooth init failed (err %d)\n", err);
        return err;
    }
    printk("Bluetooth initialized\n");

    // Start advertising
    bt_gatt_service_register(&audio_service);
    bt_gatt_service_register(&bas_service);
    err = bt_le_adv_start(BT_LE_ADV_CONN, bt_ad, ARRAY_SIZE(bt_ad), bt_sd, ARRAY_SIZE(bt_sd));
    if (err)
    {
        printk("Advertising failed to start (err %d)\n", err);
        return err;
    }
    else
    {
        printk("Advertising successfully started\n");
    }

    // Start pusher
    ring_buf_init(&ring_buf, sizeof(tx_queue), tx_queue);
    k_thread_create(&pusher_thread, pusher_stack, K_THREAD_STACK_SIZEOF(pusher_stack), (k_thread_entry_t)pusher, NULL, NULL, NULL, K_PRIO_PREEMPT(7), 0, K_NO_WAIT);

    return 0;
}

struct bt_conn *get_current_connection()
{
    return current_connection;
}

int broadcast_audio_packets(uint8_t *buffer, size_t size)
{
    while (!write_to_tx_queue(buffer, size))
    {
        k_sleep(K_MSEC(1));
    }
    return 0;
}

void set_transport_callbacks(struct transport_cb *_callbacks)
{
    external_callbacks = _callbacks;
}

void set_allowed(bool allowed)
{
    if (is_allowed != allowed)
    {
        is_allowed = allowed;
        uint8_t value[1] = {(is_allowed ? 1 : 0)};
        bt_gatt_notify(NULL, &audio_service.attrs[6], &value, 1);
    }
}

void set_bt_batterylevel(uint8_t level)
{
    if (battery_level != level)
    {
        battery_level = level;
        bt_gatt_notify(NULL, &bas_service.attrs[1], &level, sizeof(level));
    }
}