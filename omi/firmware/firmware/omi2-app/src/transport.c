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
#include "transport.h"
#include "config.h"
#include "utils.h"
#include "sdcard.h"
#include "storage.h"
#include "button.h"
#include "mic.h"
#include "battery.h" 

LOG_MODULE_REGISTER(transport, CONFIG_LOG_DEFAULT_LEVEL);

// Forward declarations
static bool push_to_gatt(struct bt_conn *conn);
bool write_to_storage(void);
void update_file_size(void);
extern void set_test_mode(bool enable_test_mode);

/**
 * Forward declarations for handler functions
 */
static void audio_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t audio_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);
static ssize_t audio_codec_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);
static void dfu_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t dfu_control_point_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags);
static void test_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t test_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);
static ssize_t test_data_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags);

// Helper function to convert PHY to string
static const char *phy2str(uint8_t phy)
{
    switch (phy) {
    case BT_GAP_LE_PHY_NONE:
        return "None";
    case BT_GAP_LE_PHY_1M:
        return "1M";
    case BT_GAP_LE_PHY_2M:
        return "2M";
    case BT_GAP_LE_PHY_CODED:
        return "Coded";
    default:
        return "Unknown";
    }
}

/** Maximum size of storage in bytes (4GB - 1 byte) */
#define MAX_STORAGE_BYTES 0xFFFF0000

extern bool is_connected; //is connected to a device
extern bool storage_is_on; //is storage enabled
extern uint8_t file_count; //number of files on the SD card
extern uint32_t file_num_array[2]; //array storing file sizes for stored audio files
struct bt_conn *current_connection = NULL; //current active Bluetooth connection
uint16_t current_mtu = 0; //current MTU (Maximum Transmission Unit) size negotiated for the BLE connection
uint16_t current_package_index = 0; //counter for packet sequence numbering to ensure ordered processing
struct k_mutex write_sdcard_mutex; //mutex for protecting SD card write operations

/**
 * Forward declarations for work items
 */
extern struct k_work_delayable battery_work;

/* Forward declaration of the MTU exchange callback */
static void exchange_mtu_cb(struct bt_conn *conn, uint8_t err,
                           struct bt_gatt_exchange_params *params);

/* Exchange parameters with callback */
static struct bt_gatt_exchange_params exchange_params = {
    .func = exchange_mtu_cb
};

/**
 * Connection Callbacks
 * 
 * This section implements the handlers for Bluetooth connection events
 * such as connections, disconnections, and parameter updates.
 */

/**
 * @brief Handler for new Bluetooth connections
 * 
 * Called when a central device establishes a connection with this peripheral.
 * Initializes connection-related state, starts periodic tasks like battery
 * level monitoring, and updates LED status.
 * 
 * @param conn The new connection that was established
 * @param err Error code (0 if successful)
 */
static void _transport_connected(struct bt_conn *conn, uint8_t err)
{
    struct bt_conn_info info = {0};
    storage_is_on = true;

    if (err) {
        LOG_ERR("Connection error: %d", err);
        return;
    }

    err = bt_conn_get_info(conn, &info);
    if (err)
    {
        LOG_ERR("Failed to get connection info (err %d)", err);
        return;
    }

    // Force MTU exchange
    err = bt_gatt_exchange_mtu(conn, &exchange_params);
    if (err) {
        LOG_ERR("MTU exchange failed: %d", err);
    }

    LOG_INF("*** BLUETOOTH CONNECTED ***");

    current_connection = bt_conn_ref(conn);
    current_mtu = info.le.data_len->tx_max_len;
    LOG_INF("Transport connected");
    LOG_INF("Interval: %d, latency: %d, timeout: %d", info.le.interval, info.le.latency, info.le.timeout);
    LOG_INF("TX PHY %s, RX PHY %s", phy2str(info.le.phy->tx_phy), phy2str(info.le.phy->rx_phy));
    LOG_INF("LE data len updated: TX (len: %d time: %d) RX (len: %d time: %d)", info.le.data_len->tx_max_len, info.le.data_len->tx_max_time, info.le.data_len->rx_max_len, info.le.data_len->rx_max_time);

    k_work_schedule(&battery_work, K_MSEC(100)); // run immediately

    is_connected = true;
    LOG_INF("Ready to send test messages - device is now connected");

#ifdef CONFIG_IMU
    // Schedule IMU data broadcasts when connected
    k_work_schedule(&imu_work, K_MSEC(IMU_REFRESH_INTERVAL));
#endif

    // // Put NFC to sleep when Bluetooth is connected
    // nfc_sleep();
}

/**
 * @brief Handler for Bluetooth disconnections
 * 
 * Called when a connection with a central device is terminated.
 * Cleans up connection-related state, stops periodic tasks,
 * and updates LED status.
 * 
 * @param conn The connection that was terminated
 * @param err Reason for disconnection
 */
static void _transport_disconnected(struct bt_conn *conn, uint8_t err)
{
    is_connected = false;
    storage_is_on = false;

    LOG_INF("*** BLUETOOTH DISCONNECTED ***");
    LOG_INF("Reason: %d", err);
    
    bt_conn_unref(conn);
    current_connection = NULL;
    current_mtu = 0;

    // // restart NFC
    // nfc_wake();
}

/**
 * @brief Handler for LE connection parameter update requests
 * 
 * Called when a connected device requests changes to the connection parameters.
 * Logs the requested parameters and allows the change.
 * 
 * @param conn The connection for which parameters are being updated
 * @param param The requested connection parameters
 * @return true to accept the parameters, false to reject
 */
static bool _le_param_req(struct bt_conn *conn, struct bt_le_conn_param *param)
{
    LOG_INF("Transport connection parameters update request received.");
    LOG_INF("Minimum interval: %d, Maximum interval: %d", param->interval_min, param->interval_max);
    LOG_INF("Latency: %d, Timeout: %d", param->latency, param->timeout);

    return true;
}

/**
 * @brief Handler for LE connection parameter updates
 * 
 * Called after connection parameters have been successfully updated.
 * Logs the new parameter values for debugging.
 * 
 * @param conn The connection with updated parameters
 * @param interval The new connection interval
 * @param latency The new connection latency
 * @param timeout The new connection supervision timeout
 */
static void _le_param_updated(struct bt_conn *conn, uint16_t interval,
                              uint16_t latency, uint16_t timeout)
{
    LOG_INF("Connection parameters updated.");
    LOG_INF("[ interval: %d, latency: %d, timeout: %d ]", interval, latency, timeout);
}

/**
 * @brief Handler for LE PHY updates
 * 
 * Called when the physical layer parameters (PHY) have been updated.
 * Used to track changes in radio configuration.
 * 
 * @param conn The connection with updated PHY
 * @param param The new PHY parameters
 */
static void _le_phy_updated(struct bt_conn *conn,
                            struct bt_conn_le_phy_info *param)
{
    LOG_INF("LE PHY updated: TX PHY %s, RX PHY %s",
           phy2str(param->tx_phy), phy2str(param->rx_phy));
}

/**
 * @brief Handler for LE data length updates
 * 
 * Called when the maximum transmission unit (MTU) size changes.
 * Updates the current_mtu variable to reflect the new maximum payload size.
 * 
 * @param conn The connection with updated data length
 * @param info The new data length parameters
 */
static void _le_data_length_updated(struct bt_conn *conn,
                                    struct bt_conn_le_data_len_info *info)
{
    LOG_INF("LE data len updated: TX (len: %d time: %d)"
           " RX (len: %d time: %d)",
           info->tx_max_len,
           info->tx_max_time, info->rx_max_len, info->rx_max_time);
    current_mtu = info->tx_max_len;
}

/**
 * @brief Callback for MTU exchange completion
 * 
 * Called when GATT MTU exchange is completed. Updates the current_mtu
 * variable with the negotiated value.
 * 
 * @param conn The connection on which MTU exchange completed
 * @param err Error code (0 if successful)
 * @param params Exchange parameters with the new MTU value
 */
static void exchange_mtu_cb(struct bt_conn *conn, uint8_t err,
                           struct bt_gatt_exchange_params *params)
{
    if (!err) {
        uint16_t mtu = bt_gatt_get_mtu(conn);
        LOG_INF("MTU exchange completed, MTU: %u", mtu);
        current_mtu = mtu - 3; // Account for ATT header (3 bytes)
    } else {
        LOG_WRN("MTU exchange failed (err %d)", err);
    }
}

/**
 * Connection callback structure containing handlers for various
 * connection-related events
 */
static struct bt_conn_cb _callback_references = {
    .connected = _transport_connected,
    .disconnected = _transport_disconnected,
    .le_param_req = _le_param_req,
    .le_param_updated = _le_param_updated,
    .le_phy_updated = _le_phy_updated,
    .le_data_len_updated = _le_data_length_updated,
};

/**
 * Service and Characteristic Definitions
 * 
 * This section defines the Bluetooth GATT services and characteristics
 * that the device exposes to connected clients.
 */

/**
 * Audio service with UUID 19B10000-E8F2-537E-4F6C-D104768A1214
 * exposes following characteristics:
 * - Audio data (UUID 19B10001-E8F2-537E-4F6C-D104768A1214) to send audio data (read/notify)
 * - Audio codec (UUID 19B10002-E8F2-537E-4F6C-D104768A1214) to send audio codec type (read)
 * - Test data (UUID 19B10003-E8F2-537E-4F6C-D104768A1214) to send test data (read/notify)
 * TODO: The current audio service UUID seems to come from old Intel sample code,
 * we should change it to UUID 814b9b7c-25fd-4acd-8604-d28877beee6d
 */

/** UUID for the audio service */
static struct bt_uuid_128 audio_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10000, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

/** UUID for the audio data characteristic (read/notify) */
static struct bt_uuid_128 audio_characteristic_data_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10001, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

/** UUID for the audio format/codec characteristic (read) */
static struct bt_uuid_128 audio_characteristic_format_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10002, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

/** UUID for the test data characteristic (read/notify) */
static struct bt_uuid_128 test_characteristic_data_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10003, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

/**
 * GATT attribute table for the audio service
 * Defines the primary service and all characteristics with their properties and permissions
 */
static struct bt_gatt_attr audio_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&audio_service_uuid),
    BT_GATT_CHARACTERISTIC(&audio_characteristic_data_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, audio_data_read_characteristic, NULL, NULL),
    BT_GATT_CCC(audio_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&audio_characteristic_format_uuid.uuid, BT_GATT_CHRC_READ, BT_GATT_PERM_READ, audio_codec_read_characteristic, NULL, NULL),
    BT_GATT_CHARACTERISTIC(&test_characteristic_data_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE, test_data_read_characteristic, test_data_write_handler, NULL),
    BT_GATT_CCC(test_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

/** Audio service definition combining all attributes */
static struct bt_gatt_service audio_service = BT_GATT_SERVICE(audio_service_attr);

/**
 * Nordic Legacy DFU service with UUID 00001530-1212-EFDE-1523-785FEABCD123
 * exposes following characteristics:
 * - Control point (UUID 00001531-1212-EFDE-1523-785FEABCD123) to start the OTA update process (write/notify)
 */

/** UUID for the Device Firmware Update service */
static struct bt_uuid_128 dfu_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001530, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));

/** UUID for the DFU control point characteristic */
static struct bt_uuid_128 dfu_control_point_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001531, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));

/**
 * GATT attribute table for the DFU service
 * Defines the DFU service and control point characteristic
 */
static struct bt_gatt_attr dfu_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&dfu_service_uuid),
    BT_GATT_CHARACTERISTIC(&dfu_control_point_uuid.uuid, BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_WRITE, NULL, dfu_control_point_write_handler, NULL),
    BT_GATT_CCC(dfu_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

/** DFU service definition combining all attributes */
static struct bt_gatt_service dfu_service = BT_GATT_SERVICE(dfu_service_attr);

/**
 * Accelerometer Data Service
 * 
 * This section implements a custom service for providing motion sensor data
 * (accelerometer and gyroscope) to connected clients via Bluetooth.
 */

//Acceleration data
//this code activates the onboard accelerometer. some cute ideas may include shaking the necklace to color strobe

/** Structure to hold sensor data readings */
static struct sensors mega_sensor;

/** Pointer to the device driver for the LSM6DSO IMU (accelerometer/gyroscope) */
static struct device *lsm6dso_dev;

/** UUID for the IMU service */
//Arbritrary uuid, feel free to change
static struct bt_uuid_128 imu_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x32403790,0x0000,0x1000,0x7450,0xBF445E5829A2));

/** UUID for the IMU data characteristic */
static struct bt_uuid_128 imu_uuid_x = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x32403791,0x0000,0x1000,0x7450,0xBF445E5829A2));

/**
 * @brief Handler for Client Characteristic Configuration changes on IMU service
 * 
 * Called when client subscribes or unsubscribes from IMU data notifications
 */
static void imu_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);

/**
 * @brief Handler for reading IMU data characteristic
 * 
 * Provides axis mode configuration information to connected clients
 */
static ssize_t imu_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);

/** Ring buffer instance for audio data */
static struct ring_buf ring_buf;

/**
 * GATT attribute table for the IMU service
 * Defines the service and data characteristic
 */
static struct bt_gatt_attr imu_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&imu_uuid),//primary description
    BT_GATT_CHARACTERISTIC(&imu_uuid_x.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, imu_data_read_characteristic, NULL, NULL),//data type
    BT_GATT_CCC(imu_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),//scheduler
};

/** IMU service definition combining all attributes */
static struct bt_gatt_service imu_service = BT_GATT_SERVICE(imu_service_attr);

/**
 * @brief Implementation of IMU data read handler
 * 
 * Returns the axis mode configuration (6 means both accelerometer and gyroscope data)
 * when clients read the characteristic.
 */
static ssize_t imu_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    LOG_INF("IMU data read characteristic");
    int axis_mode = 6; //3 for accel, 6 for (also) gyro
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &axis_mode, sizeof(axis_mode));
}


/** Interval between IMU data updates in milliseconds */
#define IMU_REFRESH_INTERVAL 1000 // 1.0 seconds

/**
 * @brief Forward declaration of IMU broadcast work handler
 * 
 * This function will be called periodically to read sensor data and send it to clients
 */
void broadcast_imu(struct k_work *work_item);

/** Delayable work item for scheduling periodic IMU data broadcasts */
K_WORK_DELAYABLE_DEFINE(imu_work, broadcast_imu);

/**
 * @brief Reads sensor data and broadcasts it to connected clients
 * 
 * Samples acceleration and gyroscope data from the sensor, updates the 
 * mega_sensor structure, and sends a notification with the data.
 * Reschedules itself to run again after the defined interval.
 */
void broadcast_imu(struct k_work *work_item) {

    sensor_sample_fetch_chan(lsm6dso_dev, SENSOR_CHAN_ACCEL_XYZ);
    sensor_channel_get(lsm6dso_dev, SENSOR_CHAN_ACCEL_X, &mega_sensor.a_x);
    sensor_channel_get(lsm6dso_dev, SENSOR_CHAN_ACCEL_Y, &mega_sensor.a_y);
    sensor_channel_get(lsm6dso_dev, SENSOR_CHAN_ACCEL_Z, &mega_sensor.a_z);

    sensor_sample_fetch_chan(lsm6dso_dev, SENSOR_CHAN_GYRO_XYZ);
    sensor_channel_get(lsm6dso_dev, SENSOR_CHAN_GYRO_X, &mega_sensor.g_x);
    sensor_channel_get(lsm6dso_dev, SENSOR_CHAN_GYRO_Y, &mega_sensor.g_y);
    sensor_channel_get(lsm6dso_dev, SENSOR_CHAN_GYRO_Z, &mega_sensor.g_z);

   //only time mega sensor is changed is through here (hopefully),  so no chance of race condition
    int err = bt_gatt_notify(current_connection, &imu_service.attrs[1], &mega_sensor, sizeof(mega_sensor));
    if (err) 
    {
       LOG_ERR("Error updating IMU data");
    }
    k_work_reschedule(&imu_work, K_MSEC(IMU_REFRESH_INTERVAL));
}

/** GPIO specification for the IMU power control pin */
static const struct gpio_dt_spec lsm6dso_en_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(lsm6dso_en_pin), gpios, {0});

/**
 * @brief Handler for Client Characteristic Configuration changes on IMU
 * 
 * Logs subscription status changes for the IMU notifications
 */
static void imu_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value) 
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
        LOG_ERR("Invalid CCC value: %u", value);
    }
}

/**
 * @brief Initialize the IMU sensor
 * 
 * Sets up the LSM6DSO IMU (accelerometer/gyroscope) sensor, configures its
 * sampling frequency, and prepares it for data acquisition.
 * 
 * @return 1 on success, 0 on failure
 */
int imu_start() 
{
    struct sensor_value odr_attr;
    const struct device *lsm6dso_dev = DEVICE_DT_GET_ONE(st_lsm6dso);
    k_msleep(50);
    if (lsm6dso_dev == NULL) 
    {
        LOG_ERR("Could not get LSM6DSO device");
        return 0;
    }
    if (!device_is_ready(lsm6dso_dev)) 
    {
        LOG_ERR("LSM6DSO: not ready");
        return 0;
    }
    
    // Set sampling frequency to 12.5 Hz
    odr_attr.val1 = 12;
    odr_attr.val2 = 500000; // 12.5 Hz

    // Make sure IMU power is enabled
    if (!device_is_ready(lsm6dso_en_pin.port)) 
    {
        LOG_ERR("IMU pin port not ready");
        return 0;
    }

    if (gpio_pin_configure_dt(&lsm6dso_en_pin, GPIO_OUTPUT_ACTIVE) < 0) 
    {
        LOG_ERR("Error configuring IMU power pin");
        return 0;
    }
    
    // Set sampling frequencies
    if (sensor_attr_set(lsm6dso_dev, SENSOR_CHAN_ACCEL_XYZ,
        SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr) < 0) 
    {
        LOG_ERR("Cannot set sampling frequency for IMU accelerometer");
        return 0;
    }
    
    if (sensor_attr_set(lsm6dso_dev, SENSOR_CHAN_GYRO_XYZ,
        SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr) < 0) {
        LOG_ERR("Cannot set sampling frequency for IMU gyroscope");
        return 0;
    }
    
    // Fetch an initial sample to ensure everything is working
    if (sensor_sample_fetch(lsm6dso_dev) < 0) 
    {
        LOG_ERR("IMU sensor sample update error");
        return 0;
    }

    LOG_INF("IMU is ready for use");
    
    return 1;
}

/**
 * @brief Power off the IMU
 * 
 * Disables power to the IMU sensor to save energy
 * when motion sensing is not needed.
 */
void imu_off()
{
    gpio_pin_set_dt(&lsm6dso_en_pin, 0);
}

/**
 * Bluetooth Advertisement Configuration
 * 
 * This section defines the advertisement and scan response data
 * that will be broadcast by the device during advertising.
 */

/**
 * Primary advertisement data containing standard fields
 */
static const struct bt_data bt_ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_UUID128_ALL, audio_service_uuid.val, sizeof(audio_service_uuid.val)),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

/**
 * Scan response data containing minimal information
 */
static const struct bt_data bt_sd[] = {
    BT_DATA_BYTES(BT_DATA_UUID16_ALL, BT_UUID_16_ENCODE(BT_UUID_DIS_VAL)),
    BT_DATA(BT_DATA_UUID128_ALL, dfu_service_uuid.val, sizeof(dfu_service_uuid.val)),
};

/**
 * Service Characteristic Handlers
 * 
 * This section implements the handlers for GATT operations on the
 * service characteristics, such as reads, writes, and notifications.
 */

/**
 * @brief Handler for Client Characteristic Configuration changes on audio service
 * 
 * Called when clients subscribe to or unsubscribe from audio data notifications.
 * Updates the service state based on client subscription status.
 * 
 * @param attr The attribute that was written
 * @param value The CCC value (BT_GATT_CCC_NOTIFY or 0)
 */
static void audio_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY)
    {
        LOG_INF("Client subscribed for audio data notifications");
        
        // Reset the ring buffer whenever subscription state changes
        ring_buf_reset(&ring_buf);
        LOG_INF("Cleared ring buffer due to subscription change");
    }
    else if (value == 0)
    {
        LOG_INF("Client unsubscribed from audio data notifications");
    }
    else
    {
        LOG_INF("Invalid CCC value: %u", value);
    }
}

/**
 * @brief Handler for reads on the audio data characteristic
 * 
 * Currently returns an empty payload as audio data is primarily sent 
 * through notifications rather than reads.
 * 
 * @param conn The connection that triggered the read
 * @param attr The attribute being read
 * @param buf Buffer to store the read data
 * @param len Maximum length to read
 * @param offset Offset to start reading from
 * @return Number of bytes read
 */
static ssize_t audio_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    LOG_INF("audio_data_read_characteristic");
    return bt_gatt_attr_read(conn, attr, buf, len, offset, NULL, 0);
}

/**
 * @brief Handler for reads on the audio codec characteristic
 * 
 * Returns the codec ID to inform clients which audio codec is in use (e.g., Opus).
 * 
 * @param conn The connection that triggered the read
 * @param attr The attribute being read
 * @param buf Buffer to store the read data
 * @param len Maximum length to read
 * @param offset Offset to start reading from
 * @return Number of bytes read
 */
static ssize_t audio_codec_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    uint8_t value[1] = {CODEC_ID};
    LOG_INF("audio_codec_read_characteristic %d", CODEC_ID);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(value));
}

/**
 * @brief Handler for Client Characteristic Configuration changes on test data characteristic
 */
static void test_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY)
    {
        LOG_INF("Client subscribed for test data notifications");
        
        // Reset the ring buffer whenever subscription state changes
        ring_buf_reset(&ring_buf);
        LOG_INF("Cleared ring buffer due to subscription change");
    }
    else if (value == 0)
    {
        LOG_INF("Client unsubscribed from test data notifications");
    }
    else
    {
        LOG_ERR("Invalid CCC value for test data: %u", value);
    }
}

/**
 * @brief Handler for reads on the test data characteristic
 */
static ssize_t test_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    const char *value = "Test Data Read Value";
    LOG_INF("test_data_read_characteristic");
    return bt_gatt_attr_read(conn, attr, buf, len, offset, value, strlen(value));
}

/**
 * @brief Handler for writes to the test data characteristic
 * 
 * Allows toggling between test mode and audio mode by writing to the test characteristic.
 * Writing "test" enables test mode, writing "audio" enables audio mode.
 * 
 * @param conn The connection that triggered the write
 * @param attr The attribute being written
 * @param buf Buffer containing the data to write
 * @param len Length of the data
 * @param offset Offset to start writing at
 * @param flags Write flags
 * @return Number of bytes written
 */
static ssize_t test_data_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
    LOG_INF("test_data_write_handler received %d bytes", len);
    
    // Create a copy of the data to ensure null-termination
    char data[32] = {0};
    size_t data_len = MIN(len, sizeof(data) - 1);
    memcpy(data, buf, data_len);
    
    LOG_INF("Received command: %s", data);
    
    // Process command
    if (strncmp(data, "test", 4) == 0) {
        LOG_INF("Enabling test mode");
        set_test_mode(true);
        
        // Send confirmation
        const char *response = "Test mode enabled";
        bt_gatt_notify(conn, attr, response, strlen(response));
    }
    else if (strncmp(data, "audio", 5) == 0) {
        LOG_INF("Enabling audio mode");
        set_test_mode(false);
        
        // Send confirmation
        const char *response = "Audio mode enabled";
        bt_gatt_notify(conn, attr, response, strlen(response));
    }
    
    return len;
}

/**
 * DFU (Device Firmware Update) Service Handlers
 * 
 * This section implements the handlers for the DFU service characteristics,
 * which enable over-the-air firmware updates.
 */

/**
 * @brief Handler for Client Characteristic Configuration changes on DFU service
 * 
 * Called when clients subscribe to or unsubscribe from DFU notifications.
 * 
 * @param attr The attribute that was written
 * @param value The CCC value (BT_GATT_CCC_NOTIFY or 0)
 */
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

/**
 * @brief Handler for writes to the DFU control point
 * 
 * Processes DFU commands from clients to initiate firmware updates.
 * When receiving valid DFU commands, triggers a system reset to enter
 * the bootloader mode for firmware updates.
 * 
 * @param conn The connection that triggered the write
 * @param attr The attribute being written
 * @param buf Buffer containing the data to write
 * @param len Length of the data
 * @param offset Offset to start writing at
 * @param flags Write flags
 * @return Number of bytes written
 */
static ssize_t dfu_control_point_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
    LOG_INF("dfu_control_point_write_handler");
    if (len == 1 && ((uint8_t *)buf)[0] == 0x06)
    {
        *(uint8_t *)&NRF_POWER->GPREGRET = 0xA8;
        NVIC_SystemReset();
    }
    else if (len == 2 && ((uint8_t *)buf)[0] == 0x01)
    {
        uint8_t notification_value = 0x10;
        bt_gatt_notify(conn, attr, &notification_value, sizeof(notification_value));

        *(uint8_t *)&NRF_POWER->GPREGRET = 0xA8;
        NVIC_SystemReset();
    }
    return len;
}

/**
 * Battery Service Handlers
 * 
 * This section implements the battery level monitoring and notification
 * functionality using the standard Bluetooth Battery Service (BAS).
 */

/** Interval between battery level updates in milliseconds */
#define BATTERY_REFRESH_INTERVAL 15000 // 15 seconds

/**
 * @brief Forward declaration of battery level broadcast work handler
 * 
 * This function will be called periodically to read battery status and send updates
 */
void broadcast_battery_level(struct k_work *work_item);

/** Delayable work item for scheduling periodic battery level broadcasts */
K_WORK_DELAYABLE_DEFINE(battery_work, broadcast_battery_level);

/**
 * @brief Reads battery level and broadcasts it via BAS
 * 
 * Queries the battery driver for current voltage and percentage,
 * then uses the Bluetooth Battery Service to notify connected clients
 * of the current battery level. Reschedules itself to run again after
 * the defined interval.
 * 
 * @param work_item The work item that triggered this call
 */
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

/**
 * Audio Data Ring Buffer
 * 
 * This section implements a ring buffer for managing audio data packets
 * that need to be transmitted over Bluetooth. The ring buffer acts as a
 * queue between the audio processing and Bluetooth transmission threads.
 */

/** Size of header before the actual payload in network packets */
#define NET_BUFFER_HEADER_SIZE 3

/** Size of header in ring buffer entries */
#define RING_BUFFER_HEADER_SIZE 2

/** Buffer holding the ring buffer data for audio transmission */
static uint8_t tx_queue[NETWORK_RING_BUF_SIZE * (CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE) * 2]; // Double the size

/** Temporary buffer for reading from the ring buffer */
static uint8_t tx_buffer[CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE];

/** Secondary buffer for writing to the ring buffer */
static uint8_t tx_buffer_2[CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE];

/** Size of data in the current tx_buffer */
static uint32_t tx_buffer_size = 0;

/**
 * @brief Write audio data to the ring buffer
 * 
 * Takes encoded audio data, prepends a size header, and adds it to
 * the ring buffer for later transmission.
 * 
 * @param data Pointer to the audio data to queue
 * @param size Size of the audio data in bytes
 * @return true if successfully queued, false if buffer full or size too large
 */
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

    // Check available space first
    uint32_t rb_size = ring_buf_size_get(&ring_buf);
    uint32_t rb_capacity = sizeof(tx_queue);
    uint32_t needed_size = CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE;
    
    if (rb_size + needed_size > rb_capacity) {
        LOG_WRN("Ring buffer almost full (%u/%u bytes), clearing older entries", 
                rb_size, rb_capacity);
        ring_buf_reset(&ring_buf);
    }

    // Write to ring buffer 
    int written = ring_buf_put(&ring_buf, tx_buffer_2, needed_size);
    if (written != needed_size)
    {
        LOG_ERR("Failed to write to ring buffer: wrote %d of %d bytes", written, needed_size);
        return false;
    }
    else
    {
        return true;
    }
}

/**
 * @brief Read audio data from the ring buffer
 * 
 * Retrieves the next audio data packet from the ring buffer,
 * extracting the size from the header.
 * 
 * @return true if data was successfully read, false if buffer empty or read error
 */
static bool read_from_tx_queue()
{
    size_t available = ring_buf_size_get(&ring_buf);
    size_t needed = CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE;
    
    // Check if there's enough data in the buffer
    if (available < needed) {
        LOG_ERR("Not enough data in ring buffer (%u/%u bytes needed)", available, needed);
        return false;
    }

    // Read from ring buffer
    tx_buffer_size = ring_buf_get(&ring_buf, tx_buffer, needed);
    if (tx_buffer_size != needed)
    {
        LOG_ERR("Failed to read from ring buffer. Expected %d bytes, got %d", needed, tx_buffer_size);
        return false;
    }

    // Adjust size
    tx_buffer_size = tx_buffer[0] + (tx_buffer[1] << 8);
    
    return true;
}

/**
 * Audio Data Pusher Thread
 * 
 * This section implements a dedicated thread that continuously pulls audio
 * data from the ring buffer and transmits it over Bluetooth or writes it
 * to storage, depending on connectivity status.
 */

/** Stack for the pusher thread */
K_THREAD_STACK_DEFINE(pusher_stack, 8192); // Increased from 4096 to 8192

/** Thread control structure for the pusher thread */
static struct k_thread pusher_thread;

/** Counter for packet sequence numbering */
static uint16_t packet_next_index = 0;

/** Temporary buffer for combining packet header and payload */
static uint8_t pusher_temp_data[CODEC_OUTPUT_MAX_BYTES + NET_BUFFER_HEADER_SIZE];

/** Counter for periodic heartbeat operations */
static uint8_t heartbeat_count = 0;

/**
 * @brief Main function for the pusher thread
 * 
 * Continuously monitors the ring buffer for audio data and handles
 * transmission over Bluetooth or writing to storage, depending on
 * connectivity status. This runs as a separate thread to ensure
 * responsive audio handling.
 */
void pusher(void)
{
    k_msleep(500);
    
    // Counter for measuring packet processing rate
    uint32_t packet_count = 0;
    uint32_t last_time_ms = k_uptime_get_32();
    uint32_t report_interval_ms = 5000; // Log stats every 5 seconds
    
    // Add a counter to limit consecutive error handling
    uint32_t consecutive_errors = 0;
    const uint32_t MAX_CONSECUTIVE_ERRORS = 10;
    
    while (1)
    {
        // Load current connection
        struct bt_conn *conn = current_connection;
        
        // If we have a connection
        if (conn)
        {
            // Use connection reference safely
            if (!bt_conn_ref(conn)) {
                LOG_ERR("Invalid connection reference");
                k_sleep(K_MSEC(20));
                continue;
            }
            
            // Check if the connection is valid and the client is subscribed to notifications
            bool valid = true;
            
            if (current_mtu < MINIMAL_PACKET_SIZE)
            {
                valid = false;
                LOG_INF("MTU too small: %d", current_mtu);
            }
            else if (!bt_gatt_is_subscribed(conn, &audio_service.attrs[1], BT_GATT_CCC_NOTIFY))
            {
                // Not subscribed to audio notifications
                valid = false;
                // Only log occasionally to reduce spam
                if (consecutive_errors == 0 || consecutive_errors >= MAX_CONSECUTIVE_ERRORS) {
                    LOG_INF("Client not subscribed to audio notifications");
                    consecutive_errors = 1; // Reset counter
                } else {
                    consecutive_errors++;
                }
            }
            
            // If everything is valid, push to GATT
            if (valid)
            {
                consecutive_errors = 0; // Reset error counter
                
                // Process up to 2 packets without yielding to ensure low latency streaming
                // (reduced from 5 to 2 to prevent buffer/stack issues)
                for (int i = 0; i < 2; i++) {
                    bool sent = false;
                    
                    // Use a try-catch pattern with k_sleep to prevent stack overflow
                    sent = push_to_gatt(conn);
                    
                    if (sent) {
                        packet_count++;
                    } else {
                        break; // No more data to send
                    }
                    
                    // Give other threads a chance to run
                    k_yield();
                }
                
                // Check if it's time to log stats
                uint32_t current_time_ms = k_uptime_get_32();
                if (current_time_ms - last_time_ms >= report_interval_ms) {
                    float time_diff_sec = (float)(current_time_ms - last_time_ms) / 1000.0f;
                    float packets_per_sec = packet_count / time_diff_sec;
                    
                    // Log streaming statistics
                    LOG_INF("Audio streaming stats: %d packets in %.1f seconds (%.1f packets/sec)",
                            packet_count, time_diff_sec, packets_per_sec);
                    
                    // Reset counters
                    packet_count = 0;
                    last_time_ms = current_time_ms;
                }
            }
            
            // Release the connection
            bt_conn_unref(conn);
            
            // Sleep for a short time to reduce CPU usage while still maintaining responsive audio
            // Increased sleep time to allow more system resources for other tasks
            k_sleep(K_MSEC(10));
        }
        // If we're not connected but storage is enabled
        else if (!storage_is_on) 
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
            
            // Sleep longer when not connected
            k_sleep(K_MSEC(20));
        }
        else
        {
            // Sleep longer when nothing to do
            k_sleep(K_MSEC(20));
        }
    }
}

/** External declaration of the storage service */
extern struct bt_gatt_service storage_service;

/**
 * Public Functions
 * 
 * This section implements the externally-accessible functions
 * that other modules can call to control Bluetooth functionality.
 */

/**
 * @brief Turn off Bluetooth radio and related subsystems
 * 
 * Disables the Bluetooth hardware, stops advertising, and powers down
 * related peripherals like SD card and microphone to save energy.
 * 
 * @return 0 on success (always returns success)
 */
int bt_off()
{
   bt_disable();
   int err = bt_le_adv_stop();
   if (err)
   {
       LOG_PRINTK("Failed to stop Bluetooth %d\n",err);
   }
   k_mutex_lock(&write_sdcard_mutex, K_FOREVER);
   sd_off();
   k_mutex_unlock(&write_sdcard_mutex);
   mic_off();
   
   // Power off the IMU to save energy
   imu_off();
   
   return 0;
}

/**
 * @brief Turn on Bluetooth radio and related subsystems
 * 
 * Enables the Bluetooth hardware, starts advertising, and powers up
 * related peripherals like SD card and microphone.
 * 
 * @return 0 on success (always returns success)
 */
int bt_on()
{
   int err = bt_enable(NULL);
   bt_le_adv_start(BT_LE_ADV_CONN, bt_ad, ARRAY_SIZE(bt_ad), bt_sd, ARRAY_SIZE(bt_sd));
   bt_gatt_service_register(&storage_service);
   sd_on();
   mic_on();

   return 0;
}

/** Maximum size for storage write operations */
#define MAX_WRITE_SIZE 440

/** Buffer for preparing data to write to storage */
static uint8_t storage_temp_data[MAX_WRITE_SIZE];

/** Padded size of each OPUS packet in storage for alignment */
#define OPUS_PADDED_LENGTH 80

/**
 * @brief Initialize the Bluetooth transport system
 * 
 * Sets up all Bluetooth services, initializes the ring buffer,
 * starts the pusher thread, and begins advertising. Also initializes
 * optional components like IMU, button, and battery
 * if they are enabled in the configuration.
 * 
 * @return 0 if successful, negative errno code if error
 */
int transport_start()
{
    // Initialize the mutex for SD card write operations
    // k_mutex_init(&write_sdcard_mutex);
    // Configure callbacks
    bt_conn_cb_register(&_callback_references);

    // Enable Bluetooth
    int err = bt_enable(NULL);
    k_msleep(1000);
    if (err)
    {
        LOG_ERR("Transport bluetooth init failed (err %d)", err);
        return err;
    }
    LOG_INF("Transport bluetooth initialized");
    
    //  Enable IMU
#ifdef CONFIG_IMU
    err = imu_start();
    if (!err) 
    {
        LOG_ERR("IMU failed to activate");
    }
    else 
    {
        LOG_INF("IMU initialized");
        bt_gatt_service_register(&imu_service);
        // Schedule the first IMU data broadcast
        k_work_schedule(&imu_work, K_MSEC(IMU_REFRESH_INTERVAL));
    }
#endif

    //  Enable button
#ifdef CONFIG_ENABLE_BUTTON
    button_init();
    register_button_service();
    activate_button_work();
#endif

    // Start advertising
    memset(storage_temp_data, 0, OPUS_PADDED_LENGTH * 4);
    bt_gatt_service_register(&storage_service);
    bt_gatt_service_register(&audio_service);
    bt_gatt_service_register(&dfu_service);
    
    // Use standard advertising parameters instead of custom ones that might be causing the error
    err = bt_le_adv_start(BT_LE_ADV_CONN, bt_ad, ARRAY_SIZE(bt_ad), bt_sd, ARRAY_SIZE(bt_sd));
    
    if (err)
    {
        LOG_ERR("Transport advertising failed to start (err %d)", err);
        return err;
    }
    else
    {
        LOG_INF("Advertising successfully started - DEVICE READY FOR CONNECTION");
        LOG_INF("Device name: %s", CONFIG_BT_DEVICE_NAME);
    }

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

    // Start pusher
    ring_buf_init(&ring_buf, sizeof(tx_queue), tx_queue);
    k_thread_create(&pusher_thread, pusher_stack, K_THREAD_STACK_SIZEOF(pusher_stack), (k_thread_entry_t)pusher, NULL, NULL, NULL, K_PRIO_PREEMPT(7), 0, K_NO_WAIT);

    return 0;
}

/**
 * @brief Get the current active Bluetooth connection
 * 
 * Returns a pointer to the currently established Bluetooth connection,
 * which can be used by other modules to send data or check connection status.
 * 
 * @return Pointer to the current bt_conn, or NULL if not connected
 */
struct bt_conn *get_current_connection()
{
    return current_connection;
}

/**
 * @brief Send encoded audio data over Bluetooth
 * 
 * Queues encoded audio data (from the codec) into the ring buffer
 * for transmission by the pusher thread. Will return an error if the buffer is full.
 * 
 * @param buffer Pointer to encoded audio data
 * @param size Size of the audio data in bytes
 * @return 0 on success, negative errno code on failure (e.g., -ENOBUFS if queue full)
 */
int broadcast_audio_packets(uint8_t *buffer, size_t size)
{
    // Only log the first few characters for binary data to reduce log spam
    static uint32_t packet_counter = 0;
    
    // Only log every 20th packet to reduce console spam
    if (packet_counter % 20 == 0) {
        char preview[16] = {0};
        int preview_len = size > 8 ? 8 : size; // Just show first few bytes
        
        // Create a safe preview string without assuming it's text
        for (int i = 0; i < preview_len; i++) {
            if (buffer[i] >= 32 && buffer[i] <= 126) {
                preview[i] = buffer[i]; // Printable ASCII
            } else {
                preview[i] = '.'; // Non-printable
            }
        }
        
        LOG_INF("Broadcasting audio packet #%d: size=%d bytes, preview=\"%s...\"", 
                packet_counter, size, preview);
    }
    packet_counter++;
    
    // Try to write to the queue with retries
    int max_retries = 3;
    for (int retry = 0; retry < max_retries; retry++) {
        if (write_to_tx_queue(buffer, size)) {
            if (packet_counter % 20 == 0) {
                LOG_INF("Successfully queued packet for transmission");
            }
            return 0; // Success
        }
        
        // If queue is full, check if we should try clearing it
        if (retry < max_retries - 1) {
            // Instead of clearing the entire buffer, try to remove oldest entries
            uint32_t rb_size = ring_buf_size_get(&ring_buf);
            uint32_t rb_capacity = sizeof(tx_queue);
            
            if (rb_size > (rb_capacity * 3/4)) {
                LOG_WRN("TX queue full, attempt %d - clearing half of the buffer", retry + 1);
                
                // Remove roughly half of the entries by reading and discarding them
                uint8_t discard_buffer[CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE];
                for (int i = 0; i < NETWORK_RING_BUF_SIZE / 2; i++) {
                    ring_buf_get(&ring_buf, discard_buffer, sizeof(discard_buffer));
                }
            } else {
                LOG_WRN("TX queue full, attempt %d - retrying", retry + 1);
            }
            
            k_sleep(K_MSEC(10)); // Brief pause before retry
        }
    }
    
    // If all retries failed, log the error and return
    LOG_WRN("TX queue full after %d retries, dropping encoded packet (%zu bytes)", 
            max_retries, size);
    return -ENOBUFS; // Indicate buffer space issue
}

/**
 * @brief Send test message directly over Bluetooth
 * 
 * Sends a test message via the test data characteristic. This function
 * bypasses the ring buffer mechanism for simpler debugging.
 * 
 * @param message Pointer to the message string
 * @param length Length of the message
 * @return 0 on success, negative error code on failure
 */
int send_test_message(const char *message, size_t length)
{
    if (!current_connection) {
        LOG_WRN("No active connection to send test message");
        return -ENOTCONN;
    }
    
    LOG_INF("Sending direct test message: \"%s\"", message);

    // Since we may not have a reliable attr_count, calculate based on array size
    const int attr_count = sizeof(audio_service_attr) / sizeof(struct bt_gatt_attr);
    
    // Find the test characteristic attribute index
    // Going through all attributes in the service to locate the test characteristic
    int test_char_idx = -1;
    for (int i = 0; i < attr_count; i++) {
        if (audio_service_attr[i].uuid == &test_characteristic_data_uuid.uuid) {
            test_char_idx = i;
            LOG_INF("Found test characteristic at index %d", i);
            break;
        }
    }
    
    if (test_char_idx < 0) {
        LOG_ERR("Could not find test characteristic in service");
        test_char_idx = 4; // Fallback to our previous guess
    }
    
    // First check if client is subscribed to the test characteristic
    bool test_subscribed = bt_gatt_is_subscribed(current_connection, &audio_service.attrs[test_char_idx], BT_GATT_CCC_NOTIFY);
    
    if (test_subscribed) {
        // Try sending directly to the test characteristic
        int err = bt_gatt_notify(current_connection, &audio_service.attrs[test_char_idx], message, length);
        
        if (err) {
            LOG_ERR("Failed to send test message notification to test characteristic: %d", err);
        } else {
            LOG_INF("Successfully sent notification to test characteristic");
            return 0;
        }
    } else {
        LOG_WRN("Client not subscribed to test characteristic (index %d)", test_char_idx);
    }
    
    // Check if subscribed to audio data characteristic as fallback
    bool audio_subscribed = bt_gatt_is_subscribed(current_connection, &audio_service.attrs[1], BT_GATT_CCC_NOTIFY);
    
    if (audio_subscribed) {
        LOG_INF("Using audio data characteristic as fallback");
        return broadcast_audio_packets((uint8_t*)message, length);
    } else {
        LOG_WRN("Client not subscribed to audio characteristic either");
        return -ENOTCONN;
    }
}

/**
 * @brief Send audio data packets to connected Bluetooth clients
 * 
 * Reads audio data from the ring buffer, fragments it into
 * appropriately-sized packets based on the current MTU,
 * and sends them via GATT notifications.
 * 
 * @param conn The connection to send data to
 * @return true if data was sent, false if no data available
 */
static bool push_to_gatt(struct bt_conn *conn)
{
    // Read data from ring buffer
    if (!read_from_tx_queue())
    {
        return false;
    }

    // Check if client is subscribed to notifications
    bool is_subscribed = bt_gatt_is_subscribed(conn, &audio_service.attrs[1], BT_GATT_CCC_NOTIFY);
    if (!is_subscribed) {
        LOG_WRN("Client not subscribed to audio data notifications, dropping packet");
        return false;
    }

    // Only log details occasionally to avoid flooding
    static uint32_t push_count = 0;
    bool should_log = (push_count % 50 == 0); // Reduced logging frequency from 20 to 50
    
    if (should_log) {
        LOG_INF("Pushing data to GATT, total size: %d (packet #%d)", tx_buffer_size, push_count);
    }
    push_count++;
    
    // For text data, we can print it out for debugging
    if (should_log) {
        char preview[17] = {0};
        int preview_len = (tx_buffer_size > 15) ? 15 : tx_buffer_size;
        
        // Create a preview string
        for (int i = 0; i < preview_len; i++) {
            char c = tx_buffer[i + RING_BUFFER_HEADER_SIZE];
            preview[i] = (c >= 32 && c <= 126) ? c : '.';
        }
        
        LOG_INF("Data preview: \"%s\"", preview);
    }
    
    uint8_t *buffer = tx_buffer + RING_BUFFER_HEADER_SIZE;
    uint16_t offset = 0;
    uint8_t index = 0;
    uint32_t packets_sent = 0;
    
    while (offset < tx_buffer_size)
    {
        // Recombine packet
        uint32_t id = packet_next_index++;
        uint32_t packet_size = MIN(current_mtu - NET_BUFFER_HEADER_SIZE, tx_buffer_size - offset);
        pusher_temp_data[0] = id & 0xFF;
        pusher_temp_data[1] = (id >> 8) & 0xFF;
        pusher_temp_data[2] = index;
        memcpy(pusher_temp_data + NET_BUFFER_HEADER_SIZE, buffer + offset, packet_size);
        
        if (should_log) {
            LOG_INF("Sending packet %d, size %d, index %d", id, packet_size, index);
        }

        offset += packet_size;
        index++;

        int retry_count = 0;
        const int max_retries = 2; // Reduced from 3 to 2
        
        while (retry_count < max_retries)
        {
            // Try send notification with timeout protection
            int err = bt_gatt_notify(conn, &audio_service.attrs[1], pusher_temp_data, packet_size + NET_BUFFER_HEADER_SIZE);

            // Log failure
            if (err)
            {
                if (should_log) {
                    LOG_ERR("bt_gatt_notify failed (err %d)", err);
                    LOG_INF("MTU: %d, packet_size: %d", current_mtu, packet_size + NET_BUFFER_HEADER_SIZE);
                }
                
                if (err == -EAGAIN || err == -ENOMEM) {
                    retry_count++;
                    k_sleep(K_MSEC(10)); // Increased from 5ms to 10ms
                    continue;
                } else {
                    // For other errors, break out of the retry loop
                    break;
                }
            }
            else
            {
                packets_sent++;
                if (should_log) {
                    LOG_INF("Notification sent successfully");
                }
                break; // Success - exit retry loop
            }
        }
        
        // Add a small delay between packets to prevent buffer allocation issues
        k_sleep(K_MSEC(2));
    }

    // Check if ring buffer is getting full and clear it if needed
    uint32_t rb_size = ring_buf_size_get(&ring_buf);
    uint32_t rb_capacity = sizeof(tx_queue);
    
    if (rb_size > (rb_capacity * 2/3)) {
        LOG_WRN("Ring buffer getting full (%u/%u bytes, %u%%), clearing older entries", 
                rb_size, rb_capacity, (rb_size * 100) / rb_capacity);
                
        // Empty approximately half the buffer instead of completely resetting
        uint8_t discard_buffer[CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE];
        for (int i = 0; i < NETWORK_RING_BUF_SIZE / 2; i++) {
            if (ring_buf_size_get(&ring_buf) < sizeof(discard_buffer)) {
                break; // Exit if not enough data to discard safely
            }
            ring_buf_get(&ring_buf, discard_buffer, sizeof(discard_buffer));
        }
    }

    if (should_log) {
        LOG_INF("Finished sending all packets (%u sent)", packets_sent);
    }
    return packets_sent > 0;
}

/** Size of OPUS codec packet prefix in storage */
#define OPUS_PREFIX_LENGTH 1

/** Current offset position in the file */
static uint32_t offset = 0;

/** Current offset in the buffer for data collection */
static uint16_t buffer_offset = 0;

/**
 * @brief Write audio data to SD card storage
 * 
 * Reads audio data from the ring buffer and writes it to the SD card
 * in efficiently packed blocks. Manages partial blocks by collecting
 * data until a complete block is ready to write.
 * 
 * @return true if data was written, false if no data available
 */
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
    { //exact frame needed 
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

/** Flag indicating whether to use storage when Bluetooth is not available */
static bool use_storage = true;

/** Maximum number of audio files to store */
#define MAX_FILES 10

/** Maximum size of each audio file in bytes */
#define MAX_AUDIO_FILE_SIZE 300000

/** Counter for detecting file size update intervals */
static int recent_file_size_updated = 0;

/**
 * @brief Update file size information
 * 
 * Reads the current file size and offset information from storage
 * and updates the global file_num_array with this information.
 * This is called periodically to keep track of storage usage.
 */
void update_file_size() 
{
    file_num_array[0] = get_file_size(1);
    file_num_array[1] = get_offset();
    // LOG_PRINTK("file size for file count %d %d\n",file_count,file_num_array[0]);
    // LOG_PRINTK("offset for file count %d %d\n",file_count,file_num_array[1]);
}
