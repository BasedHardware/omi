#include "transport.h"

#include <errno.h>
#include <hal/nrf_power.h>
#include <math.h> // For float conversion in logs
#include <stdint.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/dt-bindings/gpio/nordic-nrf-gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>
#include <shell/shell_bt_nus.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/ring_buffer.h>

#include "accel.h"
#include "button.h"
#include "config.h"
#include "features.h"
#include "haptic.h"
#include "mic.h"
#ifdef CONFIG_OMI_ENABLE_MONITOR
#include "monitor.h"
#endif
#include "sd_card.h"
#include "settings.h"
#include "storage.h"
#include "rtc.h"
LOG_MODULE_REGISTER(transport, CONFIG_LOG_DEFAULT_LEVEL);

#ifdef CONFIG_OMI_ENABLE_RFSW_CTRL
static const struct gpio_dt_spec rfsw_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(rfsw_en_pin), gpios, {0});
#endif

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
extern struct bt_gatt_service storage_service;
extern bool storage_is_on;
static bool storage_full_warned = false;
#endif

extern bool is_connected;
#ifdef CONFIG_OMI_ENABLE_BATTERY
extern bool is_charging;
#endif
static atomic_t pusher_stop_flag;

struct bt_conn *current_connection = NULL;
uint16_t current_mtu = 0;
uint16_t current_package_index = 0;

static ssize_t audio_data_write_handler(struct bt_conn *conn,
                                        const struct bt_gatt_attr *attr,
                                        const void *buf,
                                        uint16_t len,
                                        uint16_t offset,
                                        uint8_t flags);

static struct bt_conn_cb _callback_references;
static void audio_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t audio_data_read_characteristic(struct bt_conn *conn,
                                              const struct bt_gatt_attr *attr,
                                              void *buf,
                                              uint16_t len,
                                              uint16_t offset);
static ssize_t audio_codec_read_characteristic(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               void *buf,
                                               uint16_t len,
                                               uint16_t offset);
static ssize_t settings_dim_ratio_write_handler(struct bt_conn *conn,
                                                const struct bt_gatt_attr *attr,
                                                const void *buf,
                                                uint16_t len,
                                                uint16_t offset,
                                                uint8_t flags);
static ssize_t settings_dim_ratio_read_handler(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               void *buf,
                                               uint16_t len,
                                               uint16_t offset);
static ssize_t settings_mic_gain_write_handler(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               const void *buf,
                                               uint16_t len,
                                               uint16_t offset,
                                               uint8_t flags);
static ssize_t settings_mic_gain_read_handler(struct bt_conn *conn,
                                              const struct bt_gatt_attr *attr,
                                              void *buf,
                                              uint16_t len,
                                              uint16_t offset);
static void charging_status_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t settings_charging_status_read_handler(struct bt_conn *conn,
                                                     const struct bt_gatt_attr *attr,
                                                     void *buf,
                                                     uint16_t len,
                                                     uint16_t offset);
static int notify_charging_status(struct bt_conn *conn, bool force_notify);
static ssize_t
features_read_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);

// Forward declarations for update functions and callbacks
static void update_phy(struct bt_conn *conn);
static void update_data_length(struct bt_conn *conn);
static void update_mtu(struct bt_conn *conn);
static void update_conn_params(struct bt_conn *conn);
static void schedule_mtu_recheck(void);
static void mtu_recheck_work_handler(struct k_work *work);
static void exchange_func(struct bt_conn *conn, uint8_t att_err, struct bt_gatt_exchange_params *params);

// --- GATT Exchange MTU Params ---
static struct bt_gatt_exchange_params exchange_params;

#define MTU_RECHECK_DELAY_MS        800
#define MTU_RECHECK_MAX_ATTEMPTS    6
static uint8_t mtu_recheck_attempts = 0;
K_WORK_DELAYABLE_DEFINE(mtu_recheck_work, mtu_recheck_work_handler);

//
// Service and Characteristic
//
// Audio service with UUID 19B10000-E8F2-537E-4F6C-D104768A1214
// exposes following characteristics:
// - Audio data (UUID 19B10001-E8F2-537E-4F6C-D104768A1214) to send audio data (read/notify)
// - Audio codec (UUID 19B10002-E8F2-537E-4F6C-D104768A1214) to send audio codec type (read)
// TODO: The current audio service UUID seems to come from old Intel sample code,
// we should change it to UUID 814b9b7c-25fd-4acd-8604-d28877beee6d
static struct bt_uuid_128 audio_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10000, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_data_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10001, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_format_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10002, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_speaker_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10003, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

static struct bt_gatt_attr audio_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&audio_service_uuid),
    BT_GATT_CHARACTERISTIC(&audio_characteristic_data_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ,
                           audio_data_read_characteristic,
                           NULL,
                           NULL),
    BT_GATT_CCC(audio_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&audio_characteristic_format_uuid.uuid,
                           BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ,
                           audio_codec_read_characteristic,
                           NULL,
                           NULL),
#ifdef CONFIG_OMI_ENABLE_SPEAKER
    BT_GATT_CHARACTERISTIC(&audio_characteristic_speaker_uuid.uuid,
                           BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_WRITE,
                           NULL,
                           audio_data_write_handler,
                           NULL),
    BT_GATT_CCC(audio_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE), //
#endif

};

static struct bt_gatt_service audio_service = BT_GATT_SERVICE(audio_service_attr);

// --- Settings Service ---
static struct bt_uuid_128 settings_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10010, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 settings_dim_ratio_characteristic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10011, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 settings_mic_gain_characteristic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10012, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 settings_charging_status_characteristic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10013, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

static struct bt_gatt_attr settings_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&settings_service_uuid),
    BT_GATT_CHARACTERISTIC(&settings_dim_ratio_characteristic_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_READ | BT_GATT_PERM_WRITE,
                           settings_dim_ratio_read_handler,
                           settings_dim_ratio_write_handler,
                           NULL),
    BT_GATT_CHARACTERISTIC(&settings_mic_gain_characteristic_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_READ | BT_GATT_PERM_WRITE,
                           settings_mic_gain_read_handler,
                           settings_mic_gain_write_handler,
                           NULL),
    BT_GATT_CHARACTERISTIC(&settings_charging_status_characteristic_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ,
                           settings_charging_status_read_handler,
                           NULL,
                           NULL),
    BT_GATT_CCC(charging_status_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

static struct bt_gatt_service settings_service = BT_GATT_SERVICE(settings_service_attr);

// --- Features Service ---
static struct bt_uuid_128 features_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10020, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 features_characteristic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10021, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

static struct bt_gatt_attr features_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&features_service_uuid),
    BT_GATT_CHARACTERISTIC(&features_characteristic_uuid.uuid,
                           BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ,
                           features_read_handler,
                           NULL,
                           NULL),
};

static struct bt_gatt_service features_service = BT_GATT_SERVICE(features_service_attr);

// --- Time Sync Service ---
// Service UUID: 19B10030-E8F2-537E-4F6C-D104768A1214
// Characteristics:
//   - Time Write (19B10031): Write 4 bytes (uint32_t epoch_s) to sync time
//   - Time Read  (19B10032): Read 4 bytes (uint32_t epoch_s) current device time
static struct bt_uuid_128 time_sync_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10030, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 time_sync_write_characteristic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10031, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 time_sync_read_characteristic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10032, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

static ssize_t time_sync_write_handler(struct bt_conn *conn,
                                       const struct bt_gatt_attr *attr,
                                       const void *buf,
                                       uint16_t len,
                                       uint16_t offset,
                                       uint8_t flags)
{
    if (len != sizeof(uint32_t)) {
        LOG_WRN("Invalid length for time sync write: %u (expected %u)", len, sizeof(uint32_t));
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    uint32_t epoch_s;
    memcpy(&epoch_s, buf, sizeof(epoch_s));

    LOG_INF("Time sync received: %u seconds", epoch_s);

    int err = rtc_set_utc_time((uint64_t)epoch_s);
    if (err) {
        LOG_ERR("Failed to set RTC time: %d", err);
        return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
    }

    LOG_INF("Time synchronized successfully");

    /* Notify SD card module so it can rename temp files to real timestamps */
    sd_notify_time_synced(epoch_s);

    return len;
}

static ssize_t time_sync_read_handler(struct bt_conn *conn,
                                      const struct bt_gatt_attr *attr,
                                      void *buf,
                                      uint16_t len,
                                      uint16_t offset)
{
    uint32_t epoch_s = get_utc_time();
    LOG_INF("Time sync read: %u seconds", epoch_s);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &epoch_s, sizeof(epoch_s));
}

static struct bt_gatt_attr time_sync_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&time_sync_service_uuid),
    BT_GATT_CHARACTERISTIC(&time_sync_write_characteristic_uuid.uuid,
                           BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_WRITE,
                           NULL,
                           time_sync_write_handler,
                           NULL),
    BT_GATT_CHARACTERISTIC(&time_sync_read_characteristic_uuid.uuid,
                           BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ,
                           time_sync_read_handler,
                           NULL,
                           NULL),
};

static struct bt_gatt_service time_sync_service = BT_GATT_SERVICE(time_sync_service_attr);

// Advertisement data
static const struct bt_data bt_ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_UUID128_ALL, audio_service_uuid.val, sizeof(audio_service_uuid.val)),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

// Scan response data
static const struct bt_data bt_sd[] = {
    BT_DATA_BYTES(BT_DATA_UUID16_ALL, BT_UUID_16_ENCODE(BT_UUID_DIS_VAL)),
};

//
// State and Characteristics
//

static void audio_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_INF("Client subscribed for notifications");
    } else if (value == 0) {
        LOG_INF("Client unsubscribed from notifications");
    } else {
        LOG_INF("Invalid CCC value: %u", value);
    }
}

static void charging_status_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    ARG_UNUSED(attr);

    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_INF("Client subscribed for charging status notifications");
        if (current_connection != NULL) {
            (void) notify_charging_status(current_connection, true);
        }
    } else if (value == 0) {
        LOG_INF("Client unsubscribed from charging status notifications");
    } else {
        LOG_INF("Invalid charging status CCC value: %u", value);
    }
}

static ssize_t audio_data_read_characteristic(struct bt_conn *conn,
                                              const struct bt_gatt_attr *attr,
                                              void *buf,
                                              uint16_t len,
                                              uint16_t offset)
{
    LOG_DBG("audio_data_read_characteristic");
    return bt_gatt_attr_read(conn, attr, buf, len, offset, NULL, 0);
}

static ssize_t audio_codec_read_characteristic(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               void *buf,
                                               uint16_t len,
                                               uint16_t offset)
{
    uint8_t value[1] = {CODEC_ID};
    LOG_DBG("audio_codec_read_characteristic %d", CODEC_ID);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(value));
}

static ssize_t audio_data_write_handler(struct bt_conn *conn,
                                        const struct bt_gatt_attr *attr,
                                        const void *buf,
                                        uint16_t len,
                                        uint16_t offset,
                                        uint8_t flags)
{
    uint16_t amount = 400;
    int16_t *int16_buf = (int16_t *) buf;
    uint8_t *data = (uint8_t *) buf;
    bt_gatt_notify(conn, attr, &amount, sizeof(amount));
    amount = speak(len, buf);
    return len;
}

static ssize_t settings_dim_ratio_write_handler(struct bt_conn *conn,
                                                const struct bt_gatt_attr *attr,
                                                const void *buf,
                                                uint16_t len,
                                                uint16_t offset,
                                                uint8_t flags)
{
    if (len != 1) {
        LOG_WRN("Invalid length for dim ratio write: %u", len);
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    uint8_t new_ratio = ((uint8_t *) buf)[0];
    if (new_ratio > 100) {
        new_ratio = 100; // Cap the value at 100
    }

    LOG_INF("Received new dim ratio: %u", new_ratio);
    int err = app_settings_save_dim_ratio(new_ratio);
    if (err) {
        LOG_ERR("Failed to save dim ratio setting: %d", err);
    }

    return len;
}

static ssize_t settings_dim_ratio_read_handler(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               void *buf,
                                               uint16_t len,
                                               uint16_t offset)
{
    uint8_t current_ratio = app_settings_get_dim_ratio();
    LOG_INF("Reading dim ratio: %u", current_ratio);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &current_ratio, sizeof(current_ratio));
}

static ssize_t settings_mic_gain_write_handler(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               const void *buf,
                                               uint16_t len,
                                               uint16_t offset,
                                               uint8_t flags)
{
    if (len != 1) {
        LOG_WRN("Invalid length for mic gain write: %u", len);
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    uint8_t new_gain = ((uint8_t *) buf)[0];
    if (new_gain > 8) {
        new_gain = 8; // Cap the value at level 8
    }

    LOG_INF("Received new mic gain level: %u", new_gain);
    int err = app_settings_save_mic_gain(new_gain);
    if (err) {
        LOG_ERR("Failed to save mic gain setting: %d", err);
    }

    // Apply the gain immediately
    mic_set_gain(new_gain);

    return len;
}

static ssize_t settings_mic_gain_read_handler(struct bt_conn *conn,
                                              const struct bt_gatt_attr *attr,
                                              void *buf,
                                              uint16_t len,
                                              uint16_t offset)
{
    uint8_t current_gain = app_settings_get_mic_gain();
    LOG_INF("Reading mic gain: %u", current_gain);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &current_gain, sizeof(current_gain));
}

static ssize_t settings_charging_status_read_handler(struct bt_conn *conn,
                                                     const struct bt_gatt_attr *attr,
                                                     void *buf,
                                                     uint16_t len,
                                                     uint16_t offset)
{
    uint8_t charging_status = is_charging ? 1U : 0U;
    LOG_INF("Reading charging status: %u", charging_status);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &charging_status, sizeof(charging_status));
}

static ssize_t
features_read_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    uint32_t features = 0;

#ifdef CONFIG_OMI_ENABLE_SPEAKER
    features |= OMI_FEATURE_SPEAKER;
#endif
#ifdef CONFIG_OMI_ENABLE_ACCELEROMETER
    features |= OMI_FEATURE_ACCELEROMETER;
#endif
#ifdef CONFIG_OMI_ENABLE_BUTTON
    features |= OMI_FEATURE_BUTTON;
#endif
#ifdef CONFIG_OMI_ENABLE_BATTERY
    features |= OMI_FEATURE_BATTERY;
#endif
#ifdef CONFIG_OMI_ENABLE_USB
    features |= OMI_FEATURE_USB;
#endif
#ifdef CONFIG_OMI_ENABLE_HAPTIC
    features |= OMI_FEATURE_HAPTIC;
#endif
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    features |= OMI_FEATURE_OFFLINE_STORAGE;
#endif
    // LED dimming is always enabled now with PWM.
    features |= OMI_FEATURE_LED_DIMMING;
    // Mic gain control is always enabled.
    features |= OMI_FEATURE_MIC_GAIN;

    return bt_gatt_attr_read(conn, attr, buf, len, offset, &features, sizeof(features));
}

// --- MTU Update Callback ---
static void exchange_func(struct bt_conn *conn, uint8_t att_err, struct bt_gatt_exchange_params *params)
{
    if (att_err) {
        LOG_ERR("MTU exchange failed (err %u)", att_err);
    } else {
        uint16_t mtu = bt_gatt_get_mtu(conn);
        LOG_INF("MTU exchange successful. New MTU: %u (Payload: %u)", mtu, mtu - 3);
        // Update current_mtu based on the negotiated value, considering header
        // Note: bt_gatt_get_mtu includes the ATT header (3 bytes)
        current_mtu = mtu; // Store the full MTU size
    }
}

//
// Battery Service Handlers
//

#ifdef CONFIG_OMI_ENABLE_BATTERY
#define BATTERY_REFRESH_INTERVAL_CONNECTED   5000 // 5 seconds
#define BATTERY_REFRESH_INTERVAL_DISCONNECTED 10000 // 10 seconds
#define CONFIG_OMI_BATTERY_CRITICAL_MV  3500  // mV
uint8_t battery_percentage = 0;
static int8_t charging_status_last_notified = -1;
void broadcast_battery_level(struct k_work *work_item);

static int notify_charging_status(struct bt_conn *conn, bool force_notify)
{
    if (conn == NULL) {
        return -ENOTCONN;
    }

    if (!bt_gatt_is_subscribed(
            conn, &settings_service.attrs[6], BT_GATT_CCC_NOTIFY)) {
        return 0;
    }

    uint8_t charging_status = is_charging ? 1U : 0U;
    if (!force_notify && charging_status_last_notified == (int8_t) charging_status) {
        return 0;
    }

    int err = bt_gatt_notify(
        conn, &settings_service.attrs[6], &charging_status, sizeof(charging_status));
    if (err) {
        LOG_WRN("Charging status notify failed: %d", err);
        return err;
    }

    charging_status_last_notified = (int8_t) charging_status;
    LOG_INF("Charging status notified: %u", charging_status);
    return 0;
}

K_WORK_DELAYABLE_DEFINE(battery_work, broadcast_battery_level);

void broadcast_battery_level(struct k_work *work_item)
{
    (void)work_item;
    uint16_t battery_millivolt;
    uint32_t next_refresh_interval =
        (is_connected && current_connection != NULL)
            ? BATTERY_REFRESH_INTERVAL_CONNECTED
            : BATTERY_REFRESH_INTERVAL_DISCONNECTED;

    if (battery_get_millivolt(&battery_millivolt) == 0 &&
        battery_get_percentage(&battery_percentage, battery_millivolt) == 0) {

        LOG_PRINTK("Battery at %d mV (capacity %d%%)\n", battery_millivolt, battery_percentage);

        if (is_connected && current_connection != NULL) {
            if (storage_transfer_active()) {
                k_work_reschedule(&battery_work, K_MSEC(next_refresh_interval));
                return;
            }

            (void) notify_charging_status(current_connection, false);

            // Use the Zephyr BAS function to set (and notify) the battery level
            int err = bt_bas_set_battery_level(battery_percentage);
            if (err) {
                LOG_ERR("Error updating battery level: %d", err);
            }
        }
        if (battery_millivolt < CONFIG_OMI_BATTERY_CRITICAL_MV) {
            LOG_WRN("Battery critical level reached (%d mV). Initiating shutdown.", battery_millivolt);
            turnoff_all();
        }
    } else {
        LOG_ERR("Failed to read battery level");
    }

    k_work_reschedule(&battery_work, K_MSEC(next_refresh_interval));
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
    if (err) {
        LOG_ERR("Failed to get connection info (err %d)", err);
        bt_conn_unref(conn);
        return;
    }

    LOG_INF("bluetooth activated");
    current_connection = bt_conn_ref(conn);
    uint16_t mtu = bt_gatt_get_mtu(conn);
    current_mtu = mtu;

    LOG_INF("Transport connected");

    // Log initial connection parameters
    double connection_interval = info.le.interval * 1.25; // in ms
    uint16_t supervision_timeout = info.le.timeout * 10;  // in ms
    LOG_INF("Initial conn params: interval %.2f ms, latency %d intervals, timeout %d ms",
            connection_interval,
            info.le.latency,
            supervision_timeout);
    LOG_INF("Initial MTU: %u", mtu);
    mtu_recheck_attempts = 0;

    // Request aggressive connection params for higher BLE sync throughput.
    update_conn_params(current_connection);

        // Delay a bit before PHY request to avoid early HCI race on some phones.
        k_sleep(K_MSEC(300));

    // Initiate PHY, Data Length, and MTU updates
    update_phy(current_connection);

    // Add a delay before data length and MTU updates as per Nordic example
    k_sleep(K_MSEC(1000));
    update_data_length(current_connection);
    update_mtu(current_connection);
    schedule_mtu_recheck();

    is_connected = true;

    if (IS_ENABLED(CONFIG_SHELL_BT_NUS)) {
        shell_bt_nus_enable(conn);
    }

    // Notify SD module about BLE connection (flush current file)
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    sd_notify_ble_state(true);
#endif
}

// Number of BLE TX slots reserved for non-audio notifications (battery, status, diagnostics).
// Audio is throttled so these slots are always available.
#define AUDIO_TX_RESERVED_SLOTS 2

// Semaphore that caps concurrent in-flight audio notifications to
// (CONFIG_BT_CONN_TX_MAX - AUDIO_TX_RESERVED_SLOTS), preserving
// AUDIO_TX_RESERVED_SLOTS buffers for battery/diagnostic/status notifs.
K_SEM_DEFINE(audio_tx_sem,
             CONFIG_BT_CONN_TX_MAX - AUDIO_TX_RESERVED_SLOTS,
             CONFIG_BT_CONN_TX_MAX - AUDIO_TX_RESERVED_SLOTS);

static void _transport_disconnected(struct bt_conn *conn, uint8_t err)
{
    k_work_cancel_delayable(&mtu_recheck_work);
    mtu_recheck_attempts = 0;

    is_connected = false;

    if (IS_ENABLED(CONFIG_SHELL_BT_NUS)) {
        shell_bt_nus_disable();
    }

    // Stop auto-sync and save current sync offset
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    sd_notify_ble_state(false);
    storage_is_on = false;
#endif

    LOG_INF("Transport disconnected");

    if (current_connection != NULL) {
        bt_conn_unref(current_connection);
        current_connection = NULL;
    }
    current_mtu = 0;
    charging_status_last_notified = -1;

    // Reset the audio TX throttle semaphore so the pusher thread is not
    // left blocked forever if it was waiting for a slot when the connection dropped.
    k_sem_init(&audio_tx_sem,
               CONFIG_BT_CONN_TX_MAX - AUDIO_TX_RESERVED_SLOTS,
               CONFIG_BT_CONN_TX_MAX - AUDIO_TX_RESERVED_SLOTS);
}

static bool _le_param_req(struct bt_conn *conn, struct bt_le_conn_param *param)
{
    LOG_INF("Transport connection parameters update request received.");
    LOG_DBG("Minimum interval: %d, Maximum interval: %d", param->interval_min, param->interval_max);
    LOG_DBG("Latency: %d, Timeout: %d", param->latency, param->timeout);

    return true;
}

static void _le_param_updated(struct bt_conn *conn, uint16_t interval, uint16_t latency, uint16_t timeout)
{
    double connection_interval = interval * 1.25; // in ms
    uint16_t supervision_timeout = timeout * 10;  // in ms
    LOG_INF("Connection parameters updated: interval %.2f ms, latency %d intervals, timeout %d ms",
            connection_interval,
            latency,
            supervision_timeout);

    if (interval > 24) {
        LOG_WRN("Connection interval still high (%u units). Re-requesting preferred params.", interval);
        update_conn_params(conn);
    }
}

static void _le_phy_updated(struct bt_conn *conn, struct bt_conn_le_phy_info *param)
{
    LOG_INF("PHY updated: TX PHY %u, RX PHY %u", param->tx_phy, param->rx_phy);
    // Detailed logging based on PHY type
    if (param->tx_phy == BT_CONN_LE_TX_POWER_PHY_1M) {
        LOG_INF("PHY updated. New PHY: 1M");
    } else if (param->tx_phy == BT_CONN_LE_TX_POWER_PHY_2M) {
        LOG_INF("PHY updated. New PHY: 2M");
    } else if (param->tx_phy == BT_CONN_LE_TX_POWER_PHY_CODED_S8) {
        LOG_INF("PHY updated. New PHY: Coded S8 (Long Range)");
    } else if (param->tx_phy == BT_CONN_LE_TX_POWER_PHY_CODED_S2) {
        LOG_INF("PHY updated. New PHY: Coded S2 (Long Range)");
    } else {
        LOG_INF("PHY updated. New PHY: Unknown (%u)", param->tx_phy);
    }
}

static void _le_data_length_updated(struct bt_conn *conn, struct bt_conn_le_data_len_info *info)
{
    LOG_INF("Data length updated: TX %u bytes/%u us, RX %u bytes/%u us",
            info->tx_max_len,
            info->tx_max_time,
            info->rx_max_len,
            info->rx_max_time);
    // Note: current_mtu is updated in exchange_func after MTU negotiation

    if (current_mtu <= 23) {
        schedule_mtu_recheck();
    }
}

static struct bt_conn_cb _callback_references = {
    .connected = _transport_connected,
    .disconnected = _transport_disconnected,
    .le_param_req = _le_param_req,
    .le_param_updated = _le_param_updated,
    .le_phy_updated = _le_phy_updated,
    .le_data_len_updated = _le_data_length_updated,
};

// --- Update Request Functions ---

#define PHY_UPDATE_RETRY_COUNT      3
#define PHY_UPDATE_RETRY_DELAY_MS   150
#define MTU_UPDATE_RETRY_COUNT      3
#define MTU_UPDATE_RETRY_DELAY_MS   120
#define CONN_PARAM_RETRY_COUNT      3
#define CONN_PARAM_RETRY_DELAY_MS   300

static void update_conn_params(struct bt_conn *conn)
{
    int err = 0;
    const struct bt_le_conn_param preferred_param = {
        .interval_min = 6,
        .interval_max = 12,
        .latency = 0,
        .timeout = 400,
    };

    LOG_INF("Requesting conn params update (7.5-15ms, latency 0)...");
    for (int attempt = 1; attempt <= CONN_PARAM_RETRY_COUNT; attempt++) {
        err = bt_conn_le_param_update(conn, &preferred_param);
        if (!err) {
            return;
        }

        if (attempt < CONN_PARAM_RETRY_COUNT) {
            LOG_WRN("bt_conn_le_param_update() failed (err %d), retry %d/%d",
                    err,
                    attempt,
                    CONN_PARAM_RETRY_COUNT);
            k_sleep(K_MSEC(CONN_PARAM_RETRY_DELAY_MS));
        }
    }

    LOG_WRN("bt_conn_le_param_update() still failed after retries (last err %d)", err);
}

static void update_phy(struct bt_conn *conn)
{
    int err = 0;
    // Prefer 2M PHY for higher throughput
    const struct bt_conn_le_phy_param preferred_phy = {
        .options = BT_CONN_LE_PHY_OPT_NONE,
        .pref_rx_phy = BT_GAP_LE_PHY_2M,
        .pref_tx_phy = BT_GAP_LE_PHY_2M,
    };

    LOG_INF("Requesting PHY update...");
    for (int attempt = 1; attempt <= PHY_UPDATE_RETRY_COUNT; attempt++) {
        err = bt_conn_le_phy_update(conn, &preferred_phy);
        if (!err) {
            if (attempt > 1) {
                LOG_INF("PHY update request accepted on retry %d", attempt);
            }
            return;
        }

        if (attempt < PHY_UPDATE_RETRY_COUNT) {
            LOG_WRN("bt_conn_le_phy_update() failed (err %d), retry %d/%d",
                    err,
                    attempt,
                    PHY_UPDATE_RETRY_COUNT);
            k_sleep(K_MSEC(PHY_UPDATE_RETRY_DELAY_MS));
        }
    }

    LOG_ERR("bt_conn_le_phy_update() failed after %d retries (last err %d)",
            PHY_UPDATE_RETRY_COUNT,
            err);
}

static void update_data_length(struct bt_conn *conn)
{
    int err;
    // Request maximum data length
    struct bt_conn_le_data_len_param data_len_param = {
        .tx_max_len = BT_GAP_DATA_LEN_MAX,
        .tx_max_time = BT_GAP_DATA_TIME_MAX,
    };
    LOG_INF("Requesting data length update...");
    err = bt_conn_le_data_len_update(conn, &data_len_param);
    if (err) {
        LOG_ERR("bt_conn_le_data_len_update() failed (err %d)", err);
    }
}

static void schedule_mtu_recheck(void)
{
    if (mtu_recheck_attempts >= MTU_RECHECK_MAX_ATTEMPTS) {
        return;
    }

    k_work_reschedule(&mtu_recheck_work, K_MSEC(MTU_RECHECK_DELAY_MS));
}

static void mtu_recheck_work_handler(struct k_work *work)
{
    ARG_UNUSED(work);

    struct bt_conn *conn = current_connection;
    if (!conn) {
        mtu_recheck_attempts = 0;
        return;
    }

    uint16_t mtu = bt_gatt_get_mtu(conn);
    current_mtu = mtu;
    if (mtu > 23) {
        LOG_INF("MTU recheck success: negotiated MTU is now %u (payload %u)", mtu, mtu - 3);
        mtu_recheck_attempts = 0;
        return;
    }

    mtu_recheck_attempts++;
    LOG_WRN("MTU still %u, re-requesting exchange (%u/%u)",
            mtu,
            mtu_recheck_attempts,
            MTU_RECHECK_MAX_ATTEMPTS);
    update_mtu(conn);

    if (mtu_recheck_attempts < MTU_RECHECK_MAX_ATTEMPTS) {
        schedule_mtu_recheck();
    }
}

static void update_mtu(struct bt_conn *conn)
{
    int err = 0;
    exchange_params.func = exchange_func; // Set the callback function

    LOG_INF("Requesting MTU exchange...");

    for (int attempt = 1; attempt <= MTU_UPDATE_RETRY_COUNT; attempt++) {
        err = bt_gatt_exchange_mtu(conn, &exchange_params);
        if (!err) {
            return;
        }

        if (err == -EALREADY) {
            uint16_t mtu = bt_gatt_get_mtu(conn);
            current_mtu = mtu;
            LOG_INF("MTU exchange already in progress/done (err %d). Using MTU: %u", err, mtu);
            return;
        }

        if ((err == -EBUSY || err == -EAGAIN) && attempt < MTU_UPDATE_RETRY_COUNT) {
            LOG_WRN("bt_gatt_exchange_mtu() busy (err %d), retry %d/%d",
                    err,
                    attempt,
                    MTU_UPDATE_RETRY_COUNT);
            k_sleep(K_MSEC(MTU_UPDATE_RETRY_DELAY_MS));
            continue;
        }

        LOG_ERR("bt_gatt_exchange_mtu() failed (err %d)", err);
        return;
    }

    LOG_ERR("bt_gatt_exchange_mtu() failed after retries (last err %d)", err);
}

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
K_SEM_DEFINE(tx_queue_sem, 0, NETWORK_RING_BUF_SIZE);

static bool write_to_tx_queue(uint8_t *data, size_t size)
{
#ifdef CONFIG_OMI_ENABLE_MONITOR
    // Increment the counter
    monitor_inc_tx_queue_write();
#endif

    if (size > CODEC_OUTPUT_MAX_BYTES) {
        return false;
    }

    // Copy data (TODO: Avoid this copy)
    tx_buffer_2[0] = size & 0xFF;
    tx_buffer_2[1] = (size >> 8) & 0xFF;
    memcpy(tx_buffer_2 + RING_BUFFER_HEADER_SIZE, data, size);

    // Write to ring buffer
    int written =
        ring_buf_put(&ring_buf,
                     tx_buffer_2,
                     (CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE)); // It always fits completely or not at all
    if (written != CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE) {
        return false;
    } else {
        k_sem_give(&tx_queue_sem);
        return true;
    }
}

static bool read_from_tx_queue()
{

    // Read from ring buffer
    // memset(tx_buffer, 0, sizeof(tx_buffer));
    uint32_t package_size = CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE;
    tx_buffer_size = ring_buf_get(&ring_buf, tx_buffer, package_size); // It always fits completely or not at all
    if (tx_buffer_size != package_size) {
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

// Called by the BT stack when an audio notification has been sent and its
// TX buffer returned to the pool. Releases the throttle semaphore slot.
static void on_audio_tx_done(struct bt_conn *conn, void *user_data)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(user_data);
    k_sem_give(&audio_tx_sem);
}

// Thread
K_THREAD_STACK_DEFINE(pusher_stack, 4096);
static struct k_thread pusher_thread;
static uint16_t packet_next_index = 0;

// Define buffer sizes based on configuration and potential MTU
#define MAX_POSSIBLE_MTU 517
static uint8_t pusher_temp_data[MAX_POSSIBLE_MTU];

static bool push_to_gatt(struct bt_conn *conn)
{
    uint8_t *buffer = tx_buffer + RING_BUFFER_HEADER_SIZE;
    uint32_t offset = 0;
    uint8_t index = 0;
    int retry_count = 0;
    const int max_retries = 3;

    while (offset < tx_buffer_size) {
        uint32_t packet_size = MIN(current_mtu - NET_BUFFER_HEADER_SIZE, tx_buffer_size - offset);

        // Block until a throttle slot is available. This preserves every audio
        // packet while still guaranteeing AUDIO_TX_RESERVED_SLOTS remain free
        // for battery/diagnostic/status notifications at all times.
        k_sem_take(&audio_tx_sem, K_FOREVER);

        uint32_t id = packet_next_index++;
        pusher_temp_data[0] = id & 0xFF;
        pusher_temp_data[1] = (id >> 8) & 0xFF;
        pusher_temp_data[2] = index;
        memcpy(pusher_temp_data + NET_BUFFER_HEADER_SIZE, buffer + offset, packet_size);

        offset += packet_size;
        index++;

        retry_count = 0;
        while (retry_count < max_retries) {
            // Try send notification with completion callback to release the throttle slot.
            // bt_gatt_notify_cb only invokes the callback when it returns 0 (success),
            // so there is no risk of double-releasing the semaphore in the error path below.
            struct bt_gatt_notify_params params = {
                .attr = &audio_service.attrs[1],
                .data = pusher_temp_data,
                .len = packet_size + NET_BUFFER_HEADER_SIZE,
                .func = on_audio_tx_done,
                .user_data = NULL,
            };
            int err = bt_gatt_notify_cb(conn, &params);
#ifdef CONFIG_OMI_ENABLE_MONITOR
            monitor_inc_gatt_notify();
#endif

            // Log failure
            if (err) {
                LOG_DBG("bt_gatt_notify_cb failed (err %d)", err);
                LOG_DBG("MTU: %d, packet_size: %d", current_mtu, packet_size + NET_BUFFER_HEADER_SIZE);
                k_sleep(K_MSEC(1));
                retry_count++;
                continue;
            }

            // Break if success (slot released in on_audio_tx_done callback)
            break;
        }

        if (retry_count >= max_retries) {
            LOG_ERR("Failed to send packet after %d retries", max_retries);
            // bt_gatt_notify_cb never succeeded so its callback will never fire;
            // release the throttle slot manually.
            k_sem_give(&audio_tx_sem);
            return false;
        }
    }

    return true;
}

#define OPUS_PREFIX_LENGTH 1
#define OPUS_PADDED_LENGTH 80
#define MAX_WRITE_SIZE 440
static uint32_t offset = 0;
static uint16_t buffer_offset = 0;

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
static uint8_t storage_temp_data[MAX_WRITE_SIZE];
bool write_to_storage(void)
{
    uint8_t *buffer = tx_buffer + 2;
    uint8_t packet_size = (uint8_t) (tx_buffer_size + OPUS_PREFIX_LENGTH);

    // buffer_offset = buffer_offset+amount_to_fill;
    // check if adding the new packet will cause a overflow
    if (buffer_offset + packet_size > MAX_WRITE_SIZE - 1) {

        storage_temp_data[buffer_offset] = tx_buffer_size;
        uint8_t *write_ptr = storage_temp_data;
        write_to_file(write_ptr, MAX_WRITE_SIZE);

        buffer_offset = packet_size;
        storage_temp_data[0] = tx_buffer_size;
        memcpy(storage_temp_data + 1, buffer, tx_buffer_size);

    } else if (buffer_offset + packet_size == MAX_WRITE_SIZE - 1) {
        // exact frame needed
        storage_temp_data[buffer_offset] = tx_buffer_size;
        memcpy(storage_temp_data + buffer_offset + 1, buffer, tx_buffer_size);
        buffer_offset = 0;
        uint8_t *write_ptr = (uint8_t *) storage_temp_data;
        write_to_file(write_ptr, MAX_WRITE_SIZE);
    } else {
        storage_temp_data[buffer_offset] = tx_buffer_size;
        memcpy(storage_temp_data + buffer_offset + 1, buffer, tx_buffer_size);
        buffer_offset = buffer_offset + packet_size;
    }

#ifdef CONFIG_OMI_ENABLE_MONITOR
    monitor_inc_storage_write();
#endif
    return true;
}
#endif

static bool use_storage = true;
#define MAX_FILES 10
#define MAX_AUDIO_FILE_SIZE 300000
static int recent_file_size_updated = 0;
static uint8_t heartbeat_count = 0;

void test_pusher(void)
{
    uint32_t runs_count = 0;
    while (1) {
        k_sleep(K_MSEC(1));
        struct bt_conn *conn = current_connection;
        if (conn) {
            conn = bt_conn_ref(conn);
        }
        bool valid = true;
        if (current_mtu < MINIMAL_PACKET_SIZE) {
            valid = false;
        } else if (!conn) {
            valid = false;
        } else if (runs_count % 100 == 0) {
            valid = bt_gatt_is_subscribed(conn, &audio_service.attrs[1], BT_GATT_CCC_NOTIFY); // Check if subscribed
        }
        if (valid) {
            // Expected 100 packages per seconds
            bool sent = push_to_gatt(conn);
            if (!sent) {
                // k_sleep(K_MSEC(50));
            }
        }
        if (conn) {
            bt_conn_unref(conn);
        }
        runs_count++;
        k_yield();
    }
}

void pusher(void)
{
    k_msleep(500);
    while (!atomic_get(&pusher_stop_flag)) {
        k_sem_take(&tx_queue_sem, K_FOREVER);
        if (atomic_get(&pusher_stop_flag)) {
            break;
        }

        while (read_from_tx_queue()) {
            struct bt_conn *conn = current_connection;
            bool is_subscribed = false;
            if (conn) {
                conn = bt_conn_ref(conn);
                if (current_mtu >= MINIMAL_PACKET_SIZE) {
                    is_subscribed = bt_gatt_is_subscribed(conn, &audio_service.attrs[1], BT_GATT_CCC_NOTIFY);
                }
            }

            if (conn && is_subscribed) {
                push_to_gatt(conn);
                bt_conn_unref(conn);
            } else if (!conn) {
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
                if (get_file_size() < MAX_STORAGE_BYTES && is_sd_on()) {
                    storage_full_warned = false;
                    write_to_storage();
                } else {
                    if (!storage_full_warned) {
                        LOG_WRN("Storage full, stopping offline storage");
                        storage_full_warned = true;
                    }
                }
#endif
            } else {
                bt_conn_unref(conn);
                k_sleep(K_MSEC(10));
            }
        }
    }
}

int transport_off()
{
    // Stop pusher thread when transport is turned off
    atomic_set(&pusher_stop_flag, 1);
    k_sem_give(&tx_queue_sem);
    int ret = k_thread_join(&pusher_thread, K_MSEC(500));
    if (ret != 0) {
        LOG_WRN("Pusher thread did not terminate in time (err %d)", ret);
        k_thread_abort(&pusher_thread);
        LOG_WRN("Pusher thread aborted during transport_off");
    }

    // First disconnect any active connections
    if (current_connection != NULL) {
        bt_conn_disconnect(current_connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        bt_conn_unref(current_connection);
        current_connection = NULL;
    }

    // Stop advertising
    int err = bt_le_adv_stop();
    if (err) {
        LOG_ERR("Failed to stop Bluetooth advertising %d", err);
    }

    // Disable Bluetooth
    err = bt_disable();
    if (err) {
        LOG_ERR("Failed to disable Bluetooth %d", err);
    }

    // Pull the rfsw control low
#ifdef CONFIG_OMI_ENABLE_RFSW_CTRL
    err = gpio_pin_set_dt(&rfsw_en, 0);
    if (err) {
        LOG_ERR("Failed to pull the rfsw control low %d", err);
    }
#endif

    // Ensure all Bluetooth resources are cleaned up
    is_connected = false;
    current_mtu = 0;

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    storage_is_on = false;
#endif

    return 0;
}

// periodic advertising
int transport_start()
{
    int err = 0;

    // Pull the nfsw control high
#ifdef CONFIG_OMI_ENABLE_RFSW_CTRL
    err = gpio_pin_configure_dt(&rfsw_en, (GPIO_OUTPUT | NRF_GPIO_DRIVE_S0H1));
    if (err) {
        LOG_ERR("Failed to get the rfsw pin config (err %d)", err);
    } else {
        err = gpio_pin_set_dt(&rfsw_en, 1);
        if (err) {
            LOG_ERR("Failed to pull the rfsw pin control high (err %d)", err);
        }
    }
#endif

    // Configure callbacks
    bt_conn_cb_register(&_callback_references);

    // Enable Bluetooth
    err = bt_enable(NULL);
    if (err) {
        LOG_ERR("Transport bluetooth init failed (err %d)", err);
        return err;
    }

    LOG_INF("Transport bluetooth initialized");

    if (IS_ENABLED(CONFIG_SHELL_BT_NUS)) {
        err = shell_bt_nus_init();
        if (err) {
            LOG_ERR("BT NUS shell init failed (err %d)", err);
            return err;
        }
        LOG_INF("BT NUS shell initialized");
    }

    //  Enable accelerometer
#ifdef CONFIG_OMI_ENABLE_ACCELEROMETER
    err = accel_start();
    if (!err) {
        LOG_INF("Accelerometer failed to activate\n");
    } else {
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

// Initialize and register Haptic service if enabled
#ifdef CONFIG_OMI_ENABLE_HAPTIC
    // Note: haptic_init() is called in main.c
    register_haptic_service();
    LOG_INF("Haptic service registered via transport");
#endif

#ifdef CONFIG_OMI_ENABLE_SPEAKER
    err = speaker_init();
    if (err) {
        LOG_ERR("Speaker failed to start");
        return 0;
    }
    LOG_INF("Speaker initialized");
    register_speaker_service();

#endif

    // Start advertising
    bt_gatt_service_register(&audio_service);
    bt_gatt_service_register(&settings_service);
    bt_gatt_service_register(&features_service);
    bt_gatt_service_register(&time_sync_service);

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    // Register storage service for offline audio
    memset(storage_temp_data, 0, OPUS_PADDED_LENGTH * 4);
    bt_gatt_service_register(&storage_service);
#endif
    err = bt_le_adv_start(BT_LE_ADV_CONN, bt_ad, ARRAY_SIZE(bt_ad), bt_sd, ARRAY_SIZE(bt_sd));
    if (err) {
        LOG_ERR("Transport advertising failed to start (err %d), continuing without BLE", err);
        // Non-fatal: continue with pusher and ring buffer so offline recording works
    } else {
        LOG_INF("Advertising successfully started");
    }

#ifdef CONFIG_OMI_ENABLE_BATTERY
    int battErr = 0;
    battErr |= battery_charge_start();
    if (battErr) {
        LOG_ERR("Battery init failed (err %d)", battErr);
    } else {
        LOG_INF("Battery initialized");
    }

    k_work_schedule(&battery_work, K_MSEC(3000));
#endif

    // Start pusher
    ring_buf_init(&ring_buf, sizeof(tx_queue), tx_queue);
    if (ring_buf_is_empty(&ring_buf)) {
        LOG_INF("Ring buffer successfully initialized");
    } else {
        LOG_ERR("Ring buffer initialization failed");
        return -1;
    }

    struct k_thread *thread = k_thread_create(&pusher_thread,
                                              pusher_stack,
                                              K_THREAD_STACK_SIZEOF(pusher_stack),
                                              (k_thread_entry_t) pusher,
                                              NULL,
                                              NULL,
                                              NULL,
                                              K_PRIO_PREEMPT(7),
                                              0,
                                              K_NO_WAIT);
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
    if (!write_to_tx_queue(buffer, size)) {
        return -1;
    }
    return 0;
}
