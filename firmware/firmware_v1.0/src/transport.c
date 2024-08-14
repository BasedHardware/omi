#include <zephyr/logging/log.h>
#include <zephyr/sys/ring_buffer.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/atomic.h>
#include "lib/battery/battery.h"
#include "transport.h"
#include "config.h"
#include "utils.h"
#include "btutils.h"
#include "storage.h"

static bool reset_buf_event = true;
static uint32_t storage_action = 0;
static bool verbose = false;

//
// Internal
//

static struct bt_conn_cb _callback_references;

static void audio_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t audio_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);
static ssize_t audio_codec_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);

static void dfu_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t dfu_control_point_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags);

static ssize_t sd_storage_notify_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);
static ssize_t get_storage_action(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags);
static void sd_storage_notify_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);

//
// Service and Characteristic
//

// Dedicated to audio
// Audio service with UUID 19B10000-E8F2-537E-4F6C-D104768A1214
// exposes following characteristics:
// - Audio data (UUID 19B10001-E8F2-537E-4F6C-D104768A1214) to send audio data (read/notify)
// - Audio codec (UUID 19B10002-E8F2-537E-4F6C-D104768A1214) to send audio codec type (read)
// TODO: The current audio service UUID seems to come from old Intel sample code,
// we should change it to UUID 814b9b7c-25fd-4acd-8604-d28877beee6d
static struct bt_uuid_128 audio_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10000, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_data_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10001, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_format_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10002, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

// Dedicated to storage
// Storage service with UUID 87654321-4321-8765-4321-1234567890ab
// - Storage characteristic notify (UUID 87654321-4321-8765-4321-1234567890ac)
// - Storage characteristic read (UUID 87654321-4321-8765-4321-1234567890ad)
static struct bt_uuid_128 sd_storage_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x87654321, 0x4321, 0x8765, 0x4321, 0x1234567890ab));
static struct bt_uuid_128 sd_storage_notify_characteristic_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x87654321, 0x4321, 0x8765, 0x4321, 0x1234567890ac));
static struct bt_uuid_128 sd_storage_write_characteristic_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x87654321, 0x4321, 0x8765, 0x4321, 0x1234567890ad)); // UUID para la característica de escritura

// Audio sttributes
static struct bt_gatt_attr audio_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&audio_service_uuid),
    BT_GATT_CHARACTERISTIC(&audio_characteristic_data_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, audio_data_read_characteristic, NULL, NULL),
    BT_GATT_CCC(audio_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&audio_characteristic_format_uuid.uuid, BT_GATT_CHRC_READ, BT_GATT_PERM_READ, audio_codec_read_characteristic, NULL, NULL),
};

static struct bt_gatt_service audio_service = BT_GATT_SERVICE(audio_service_attr);

// Storage attributes
static struct bt_gatt_attr sd_storage_notify_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&sd_storage_service_uuid),
    BT_GATT_CHARACTERISTIC(&sd_storage_notify_characteristic_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, sd_storage_notify_read_characteristic, NULL, NULL),
    BT_GATT_CCC(sd_storage_notify_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&sd_storage_write_characteristic_uuid.uuid, BT_GATT_CHRC_WRITE, BT_GATT_PERM_WRITE, NULL, get_storage_action, &storage_action),
};

static struct bt_gatt_service sd_storage_notify_service = BT_GATT_SERVICE(sd_storage_notify_service_attr);

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
    BT_DATA(BT_DATA_NAME_COMPLETE, "Friend", sizeof("Friend") - 1),
};

// Scan response data
static const struct bt_data bt_sd[] = {
    BT_DATA_BYTES(BT_DATA_UUID16_ALL, BT_UUID_16_ENCODE(BT_UUID_DIS_VAL)),
    BT_DATA(BT_DATA_UUID128_ALL, dfu_service_uuid.val, sizeof(dfu_service_uuid.val)),
};

//
// State and Characteristics
//

struct bt_conn *current_connection = NULL;
uint16_t current_mtu = 0;
uint16_t current_package_index = 0;

static void audio_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY)
    {
        if(verbose) printk("Client subscribed for notifications\n");
    }
    else if (value == 0)
    {
        if(verbose) printk("Client unsubscribed from notifications\n");
    }
    else
    {
        if(verbose) printk("Invalid CCC value: %u\n", value);
    }
}

static ssize_t audio_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    if(verbose) printk("audio_data_read_characteristic\n");
    return bt_gatt_attr_read(conn, attr, buf, len, offset, NULL, 0);
}

static ssize_t audio_codec_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    if(verbose) printk("audio_codec_read_characteristic\n");
    uint8_t value[1] = {CODEC_ID};
    return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(value));
}

//
// SD storage service Handler
//

static void sd_storage_notify_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY)
    {
        if(verbose) printk("Client subscribed for SD Storage notifications\n");
    }
    else if (value == 0)
    {
        if(verbose) printk("Client unsubscribed from SD Storage notifications\n");
    }
    else
    {
        if(verbose) printk("Invalid CCC value for SD Storage: %u\n", value);
    }
}

static ssize_t sd_storage_notify_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &notification_value, sizeof(notification_value));
}

static ssize_t get_storage_action(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags) 
{
    if (len != sizeof(storage_action)) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }
    storage_action = *(const uint16_t *)buf;
    return len;
}

//
// DFU Service Handlers
//

static void dfu_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY)
    {
        if(verbose) printk("Client subscribed for notifications\n");
    }
    else if (value == 0)
    {
        if(verbose) printk("Client unsubscribed from notifications\n");
    }
    else
    {
        if(verbose) printk("Invalid CCC value: %u\n", value);
    }
}

static ssize_t dfu_control_point_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
    if(verbose) printk("dfu_control_point_write_handler\n");
    if (len == 1 && ((uint8_t *)buf)[0] == 0x06)
    {
        NRF_POWER->GPREGRET = 0xA8;
        NVIC_SystemReset();
    }
    else if (len == 2 && ((uint8_t *)buf)[0] == 0x01)
    {
        uint8_t notification_value = 0x10;
        bt_gatt_notify(conn, attr, &notification_value, sizeof(notification_value));

        NRF_POWER->GPREGRET = 0xA8;
        NVIC_SystemReset();
    }
    return len;
}

//
// Battery Service Handlers
//

struct k_work battery_work;

void broadcast_battery_level(struct k_work *work_item) {
    uint16_t battery_millivolt;
    uint8_t battery_percentage;

    if (battery_get_millivolt(&battery_millivolt) == 0 &&
        battery_get_percentage(&battery_percentage, battery_millivolt) == 0) {

        if(verbose) printk("Battery at %d mV (capacity %d%%)\n", battery_millivolt, battery_percentage);

        // Use the Zephyr BAS function to set (and notify) the battery level
        int err = bt_bas_set_battery_level(battery_percentage);
        if (err) {
            if(verbose) printk("Error updating battery level: %d\n", err);
        }
    } else {
        if(verbose) printk("Failed to read battery level\n");
    }
}

//
// Connection Callbacks
//

static void _transport_connected(struct bt_conn *conn, uint8_t err)
{
    struct bt_conn_info info = {0};

    err = bt_conn_get_info(conn, &info);
    if (err)
    {
        if(verbose) printk("Failed to get connection info (err %d)\n", err);
        return;
    }
    
    reset_buf_event = true;
    
    current_connection = bt_conn_ref(conn);
    current_mtu = info.le.data_len->tx_max_len;
    if(verbose) printk("\n");
    if(verbose) printk("Interval: %d, latency: %d, timeout: %d\n", info.le.interval, info.le.latency, info.le.timeout);
    if(verbose) printk("TX PHY %s, RX PHY %s\n", phy2str(info.le.phy->tx_phy), phy2str(info.le.phy->rx_phy));
    if(verbose) printk("LE data len updated: TX (len: %d time: %d) RX (len: %d time: %d)\n", info.le.data_len->tx_max_len, info.le.data_len->tx_max_time, info.le.data_len->rx_max_len, info.le.data_len->rx_max_time);

    k_work_submit(&battery_work);
}

static void _transport_disconnected(struct bt_conn *conn, uint8_t err)
{
    if(verbose) printk("Disconnected\n");
    current_connection = NULL;
    reset_buf_event = true;
    bt_conn_unref(conn);
    storage_action = 0;
    current_mtu = 0;
}

static bool _le_param_req(struct bt_conn *conn, struct bt_le_conn_param *param)
{
    if(verbose) printk("Connection parameters update request received.\n");
    if(verbose) printk("Minimum interval: %d, Maximum interval: %d\n",
                param->interval_min, param->interval_max);
    if(verbose) printk("Latency: %d, Timeout: %d\n", param->latency, param->timeout);

    return true;
}

static void _le_param_updated(struct bt_conn *conn, uint16_t interval,
                              uint16_t latency, uint16_t timeout)
{
    if(verbose) printk("Connection parameters updated.\n"
                " interval: %d, latency: %d, timeout: %d\n",
                interval, latency, timeout);
}

static void _le_phy_updated(struct bt_conn *conn,
                            struct bt_conn_le_phy_info *param)
{
    if(verbose) printk("LE PHY updated: TX PHY %s, RX PHY %s\n",
                phy2str(param->tx_phy), phy2str(param->rx_phy));
}

static void _le_data_length_updated(struct bt_conn *conn,
                                    struct bt_conn_le_data_len_info *info)
{
    if(verbose) printk("LE data len updated: TX (len: %d time: %d)"
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
        if(verbose) printk("Failed to read from ring buffer %d\n", tx_buffer_size);
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

    if (storage_action != 1)
    {
        return false;
    }

    printf("Sending audio...\n");

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

            int err = bt_gatt_notify(conn, &audio_service.attrs[1], pusher_temp_data, packet_size + NET_BUFFER_HEADER_SIZE); // Try send notification
            
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

static bool push_to_storage(struct bt_conn *conn)
{
    // Read data from ring buffer
    if (!read_from_tx_queue())
    {
        return false;
    }

    if (storage_action != 0)
    {
        return false;
    }

    //printf("Saving files...\n");

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
            int ret = save_audio_in_storage(pusher_temp_data, packet_size + NET_BUFFER_HEADER_SIZE);

            if(ret < 0)
            {
                continue;
            }

            break;
        }
    }

    return true;
}

uint32_t id = 0;

int read_audio_in_storage(void)
{
    if(storage_action == 2 && notification_value > -1)
	{
        char *file = (char *)malloc(20);

        snprintf(file, 20, "audio/%u.txt", notification_value + 1);

        printf("Sending files...\n");

        size_t index = 0;

        while (1)
        {
			ReadParams audio_frame = read_file_fragmment(file, 651,(651*(index))+index);
            if(audio_frame.ret != 651)
            {
                if(notification_value > -1)
                {
                    char *prev_file = (char *)malloc(30);
                    snprintf(prev_file, 30, "audio/%u.txt,status:OK", notification_value + 1);
                    notification_value = notification_value - 1;
                    write_info(prev_file);
                    free(prev_file);
                } 
                else if(notification_value < 0)
                {
                    write_info("");
                }

                delete_file(file);
                
                free(file);

                return -2;
            }

            if(!current_connection)
            {
                return -1;
            }

            size_t size;
            
            char *revert = revert_format(audio_frame.data);
            audio_frame.data = NULL;
            uint8_t *audio = convert_to_uint8_array(revert, &size);
            free(revert);

            for(uint8_t i = 0; i < 2; i++)
            {
                bt_gatt_notify(current_connection, &audio_service.attrs[1], audio, size); // Try send notification
            }
            

            free(audio);

            index++;
		}

        free(file);

        return 0;
	}
    
    return -1;
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
            if (storage_action < 0 || storage_action > 1 || reset_buf_event)
            {
                ring_buf_reset(&ring_buf);
                reset_buf_event = false;
                k_sleep(K_MSEC(10));
            }
        }

        // Handle GATT && STORAGE
        if (use_gatt && valid)
        {
            bool sent = push_to_gatt(conn);
            if (!sent) k_sleep(K_MSEC(50));
        } else
        {
            if(!reset_buf_event)
            {
                bool sent = push_to_storage(conn);
                if (!sent) k_sleep(K_MSEC(50));
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
        if(verbose) printk("Bluetooth init failed (err %d)\n", err);
        return err;
    }
    if(verbose) printk("Bluetooth initialized\n");

    // Start advertising
    bt_gatt_service_register(&audio_service);
    bt_gatt_service_register(&dfu_service);
    bt_gatt_service_register(&sd_storage_notify_service);
    err = bt_le_adv_start(BT_LE_ADV_CONN, bt_ad, ARRAY_SIZE(bt_ad), bt_sd, ARRAY_SIZE(bt_sd));
    if (err)
    {
        if(verbose) printk("Advertising failed to start (err %d)\n", err);
        return err;
    }
    else
    {
        if(verbose) printk("Advertising successfully started\n");
    }

    int battErr = 0;

	battErr |= battery_init();
	battErr |= battery_charge_start();

	if (battErr)
	{
		if(verbose) printk("Battery init failed (err %d)\n", battErr);
	}
	else
	{
		if(verbose) printk("Battery initialized\n");
	}

    k_work_init(&battery_work, broadcast_battery_level);

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