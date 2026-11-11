#include "transport.h"

#include <errno.h>
#include <hal/nrf_power.h>
#include <math.h> // For float conversion in logs
#include <shell/shell_bt_nus.h>
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
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/ring_buffer.h>

#include "accel.h"
#include "battery_guard.h"
#include "button.h"
#include "config.h"
#include "custody.h"
#include "diagnostics.h"
#include "features.h"
#include "haptic.h"
#include "lib/battery/battery.h"
#include "mic.h"
#include "recovery_diagnostics.h"
#ifdef CONFIG_OMI_ENABLE_MONITOR
#include "monitor.h"
#endif
#include "capture_mute.h"
#include "capture_mute_gatt.h"
#include "power_control_gatt.h"
#include "rtc.h"
#include "sd_card.h"
#include "settings.h"
#include "storage.h"
#include "unit_id.h"
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
extern bool is_off;
#ifdef CONFIG_OMI_ENABLE_BATTERY
extern bool is_charging;
#endif
static atomic_t pusher_stop_flag;
static bool advertising_started;

bool transport_advertising_started(void)
{
    return advertising_started;
}

struct bt_conn *current_connection = NULL;
static struct k_spinlock connection_lock;
uint16_t current_mtu = 0;
uint16_t current_package_index = 0;

#ifdef CONFIG_OMI_ENABLE_SPEAKER
static ssize_t audio_data_write_handler(struct bt_conn *conn,
                                        const struct bt_gatt_attr *attr,
                                        const void *buf,
                                        uint16_t len,
                                        uint16_t offset,
                                        uint8_t flags);
#endif

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
static ssize_t settings_mute_write_handler(struct bt_conn *conn,
                                           const struct bt_gatt_attr *attr,
                                           const void *buf,
                                           uint16_t len,
                                           uint16_t offset,
                                           uint8_t flags);
static ssize_t settings_mute_read_handler(struct bt_conn *conn,
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
static ssize_t settings_device_name_write_handler(struct bt_conn *conn,
                                                  const struct bt_gatt_attr *attr,
                                                  const void *buf,
                                                  uint16_t len,
                                                  uint16_t offset,
                                                  uint8_t flags);
static ssize_t settings_device_name_read_handler(struct bt_conn *conn,
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
static void adv_name_update_work_handler(struct k_work *work);
static void exchange_func(struct bt_conn *conn, uint8_t att_err, struct bt_gatt_exchange_params *params);

// --- GATT Exchange MTU Params ---
static struct bt_gatt_exchange_params exchange_params;

#define MTU_RECHECK_DELAY_MS 800
#define MTU_RECHECK_MAX_ATTEMPTS 6
static uint8_t mtu_recheck_attempts = 0;
K_WORK_DELAYABLE_DEFINE(mtu_recheck_work, mtu_recheck_work_handler);

/* BLE power-off worker: never run the blocking shutdown on the system workqueue. */
static atomic_t power_off_pending = ATOMIC_INIT(0);
K_SEM_DEFINE(power_off_sem, 0, 1);

static bool power_control_off_pending(void)
{
    return atomic_get(&power_off_pending) != 0;
}

static int power_control_schedule_off(void)
{
    if (atomic_cas(&power_off_pending, 0, 1)) {
        k_sem_give(&power_off_sem);
    }
    return 0;
}

static void power_off_thread_fn(void *p1, void *p2, void *p3)
{
    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);
    while (1) {
        k_sem_take(&power_off_sem, K_FOREVER);
        /* Allow the ATT response to be queued before BLE is torn down. */
        k_msleep(50);
        LOG_INF("Executing BLE-requested orderly shutdown");
        turnoff_all();
    }
}

/* Recovery must not start a backlog application worker before mode selection. */
K_THREAD_DEFINE(power_off_thread, 2048, power_off_thread_fn, NULL, NULL, NULL, 5, 0, SYS_FOREVER_MS);
/* End BLE power-off worker. */

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
#ifdef CONFIG_OMI_ENABLE_SPEAKER
static struct bt_uuid_128 audio_characteristic_speaker_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10003, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
#endif

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
static struct bt_uuid_128 settings_mute_characteristic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10015, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

static struct bt_uuid_128 settings_power_control_characteristic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10016, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

static ssize_t settings_power_control_write_handler(struct bt_conn *conn,
                                                    const struct bt_gatt_attr *attr,
                                                    const void *buf,
                                                    uint16_t len,
                                                    uint16_t offset,
                                                    uint8_t flags)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(flags);
    return power_control_gatt_write(buf, len, offset);
}

static ssize_t settings_power_control_read_handler(struct bt_conn *conn,
                                                   const struct bt_gatt_attr *attr,
                                                   void *buf,
                                                   uint16_t len,
                                                   uint16_t offset)
{
    uint8_t state = power_control_gatt_state(is_off);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &state, sizeof(state));
}

static struct bt_uuid_128 settings_device_name_characteristic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10014, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

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
    /* Appended so charging notify stays on attrs[6]. */
    BT_GATT_CHARACTERISTIC(&settings_mute_characteristic_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_READ | BT_GATT_PERM_WRITE,
                           settings_mute_read_handler,
                           settings_mute_write_handler,
                           NULL),
    /* Append to preserve the charging notification's attrs[6]. */
    BT_GATT_CHARACTERISTIC(&settings_power_control_characteristic_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_READ | BT_GATT_PERM_WRITE,
                           settings_power_control_read_handler,
                           settings_power_control_write_handler,
                           NULL),
    BT_GATT_CHARACTERISTIC(&settings_device_name_characteristic_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_READ | BT_GATT_PERM_WRITE,
                           settings_device_name_read_handler,
                           settings_device_name_write_handler,
                           NULL),
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

    int err = rtc_set_utc_time((uint64_t) epoch_s);
    if (err) {
        LOG_ERR("Failed to set RTC time: %d", err);
        return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
    }

    LOG_INF("Time synchronized successfully");

    /* Notify SD card module so it can rename temp files to real timestamps */
    sd_notify_time_synced(epoch_s);

    return len;
}

static ssize_t
time_sync_read_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
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

/* Appended after the existing dynamic services on normal boots. */
static struct bt_uuid_128 diagnostics_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10040, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 diagnostics_characteristic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10041, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

static struct bt_uuid_128 recovery_diagnostics_characteristic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10042, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

/* Recovery also needs a coherent value across ATT Read Blob requests. */
static struct {
    bool valid;
    uint8_t value[OMI_RECOVERY_DIAGNOSTICS_SIZE];
} recovery_read_cache[CONFIG_BT_MAX_CONN];
K_MUTEX_DEFINE(recovery_read_lock);

static void recovery_reset_read_cache(struct bt_conn *conn)
{
    if (conn && bt_conn_index(conn) < ARRAY_SIZE(recovery_read_cache)) {
        k_mutex_lock(&recovery_read_lock, K_FOREVER);
        recovery_read_cache[bt_conn_index(conn)].valid = false;
        k_mutex_unlock(&recovery_read_lock);
    }
}

static void recovery_connected(struct bt_conn *conn, uint8_t err)
{
    ARG_UNUSED(err);
    recovery_reset_read_cache(conn);
}

static void recovery_disconnected(struct bt_conn *conn, uint8_t reason)
{
    ARG_UNUSED(reason);
    recovery_reset_read_cache(conn);
}

/* SAFE omits application callbacks, but still invalidates diagnostic caches. */
static struct bt_conn_cb recovery_callbacks = {
    .connected = recovery_connected,
    .disconnected = recovery_disconnected,
};

static ssize_t recovery_diagnostics_read(struct bt_conn *conn,
                                         const struct bt_gatt_attr *attr,
                                         void *buf,
                                         uint16_t len,
                                         uint16_t offset)
{
    if (offset > OMI_RECOVERY_DIAGNOSTICS_SIZE) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    if (!conn || bt_conn_index(conn) >= ARRAY_SIZE(recovery_read_cache)) {
        return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
    }
    uint8_t index = bt_conn_index(conn);
    uint8_t value[OMI_RECOVERY_DIAGNOSTICS_SIZE];
    k_mutex_lock(&recovery_read_lock, K_FOREVER);
    if (offset == 0 || !recovery_read_cache[index].valid) {
        recovery_diagnostics_snapshot(recovery_read_cache[index].value);
        recovery_read_cache[index].valid = true;
    }
    memcpy(value, recovery_read_cache[index].value, sizeof(value));
    k_mutex_unlock(&recovery_read_lock);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(value));
}

/* One snapshot per connection. A new offset-zero read starts a new snapshot.
 * The read callback does not identify the ATT bearer, so do not silently
 * enable EATT with a connection-wide cache. */
BUILD_ASSERT(!IS_ENABLED(CONFIG_BT_EATT), "Diagnostics long reads require a single ATT bearer");

static struct {
    bool valid;
    uint8_t value[OMI_DIAGNOSTICS_SIZE];
} diagnostics_read_cache[CONFIG_BT_MAX_CONN];
static struct k_spinlock diagnostics_read_lock;

static void diagnostics_reset_read_cache(struct bt_conn *conn)
{
    recovery_reset_read_cache(conn);
    if (conn == NULL) {
        return;
    }
    uint8_t index = bt_conn_index(conn);
    if (index >= ARRAY_SIZE(diagnostics_read_cache)) {
        return;
    }
    k_spinlock_key_t key = k_spin_lock(&diagnostics_read_lock);
    diagnostics_read_cache[index].valid = false;
    k_spin_unlock(&diagnostics_read_lock, key);
}

static ssize_t diagnostics_read_handler(struct bt_conn *conn,
                                        const struct bt_gatt_attr *attr,
                                        void *buf,
                                        uint16_t len,
                                        uint16_t offset)
{
    if (offset > OMI_DIAGNOSTICS_SIZE) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    if (conn == NULL) {
        return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
    }
    uint8_t index = bt_conn_index(conn);
    if (index >= ARRAY_SIZE(diagnostics_read_cache)) {
        return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
    }

    uint8_t value[OMI_DIAGNOSTICS_SIZE];
    k_spinlock_key_t key = k_spin_lock(&diagnostics_read_lock);
    if (offset == 0 || !diagnostics_read_cache[index].valid) {
        struct omi_diagnostics_snapshot snapshot;
        omi_diagnostics_snapshot(&snapshot);
        omi_diagnostics_pack(diagnostics_read_cache[index].value, &snapshot);
        diagnostics_read_cache[index].valid = true;
    }
    memcpy(value, diagnostics_read_cache[index].value, sizeof(value));
    k_spin_unlock(&diagnostics_read_lock, key);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(value));
}

static struct bt_gatt_attr diagnostics_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&diagnostics_service_uuid),
    BT_GATT_CHARACTERISTIC(&diagnostics_characteristic_uuid.uuid,
                           BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ,
                           diagnostics_read_handler,
                           NULL,
                           NULL),
    BT_GATT_CHARACTERISTIC(&recovery_diagnostics_characteristic_uuid.uuid,
                           BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ,
                           recovery_diagnostics_read,
                           NULL,
                           NULL),
};
static struct bt_gatt_service diagnostics_service = BT_GATT_SERVICE(diagnostics_service_attr);

/* SAFE does not expose normal telemetry or install application callbacks. */
static struct bt_gatt_attr safe_diagnostics_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&diagnostics_service_uuid),
    BT_GATT_CHARACTERISTIC(&recovery_diagnostics_characteristic_uuid.uuid,
                           BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ,
                           recovery_diagnostics_read,
                           NULL,
                           NULL),
};
static struct bt_gatt_service safe_diagnostics_service = BT_GATT_SERVICE(safe_diagnostics_service_attr);

// Advertisement data
static const struct bt_data bt_ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_UUID128_ALL, audio_service_uuid.val, sizeof(audio_service_uuid.val)),
};

/* BLE RX publishes only pending bytes. HCI calls consume a worker-local snapshot. */
static char adv_device_name[MAX_DEVICE_NAME_LEN] = CONFIG_BT_DEVICE_NAME;
static struct k_spinlock adv_name_lock;
static struct k_work_delayable adv_name_update_work;
static uint32_t adv_name_generation;
static bool adv_name_pending;
static uint8_t adv_name_retries;
#define ADV_NAME_RETRY_LIMIT 5
#define ADV_NAME_RETRY_MS 100

static int apply_advertising_name(bool start)
{
    char snapshot[MAX_DEVICE_NAME_LEN];
    k_spinlock_key_t key = k_spin_lock(&adv_name_lock);
    memcpy(snapshot, adv_device_name, sizeof(snapshot));
    uint32_t generation = adv_name_generation;
    k_spin_unlock(&adv_name_lock, key);

    /* The name and length stay immutable for both synchronous Bluetooth calls. */
    const struct bt_data scan_response[] = {
        BT_DATA_BYTES(BT_DATA_UUID16_ALL, BT_UUID_16_ENCODE(BT_UUID_DIS_VAL)),
        BT_DATA(BT_DATA_NAME_COMPLETE, snapshot, strlen(snapshot)),
    };
#if defined(CONFIG_BT_DEVICE_NAME_DYNAMIC)
    int err = bt_set_name(snapshot);
    if (err) {
        return err;
    }
#endif
    int result;
    if (start) {
        result = bt_le_adv_start(BT_LE_ADV_CONN, bt_ad, ARRAY_SIZE(bt_ad), scan_response, ARRAY_SIZE(scan_response));
    } else {
        result = bt_le_adv_update_data(bt_ad, ARRAY_SIZE(bt_ad), scan_response, ARRAY_SIZE(scan_response));
    }
    if (!result) {
        key = k_spin_lock(&adv_name_lock);
        /* A write during HCI must retain its pending update and scheduled work. */
        if (generation == adv_name_generation) {
            adv_name_pending = false;
        }
        k_spin_unlock(&adv_name_lock, key);
    }
    return result;
}

static void adv_name_update_work_handler(struct k_work *work)
{
    ARG_UNUSED(work);
    int err = apply_advertising_name(false);
    bool retry = false;
    k_spinlock_key_t key = k_spin_lock(&adv_name_lock);
    if (err == -EAGAIN && adv_name_pending && adv_name_retries < ADV_NAME_RETRY_LIMIT) {
        ++adv_name_retries;
        retry = true;
    }
    k_spin_unlock(&adv_name_lock, key);
    if (retry) {
        k_work_reschedule(&adv_name_update_work, K_MSEC(ADV_NAME_RETRY_MS));
        return;
    }
    if (err) {
        /* Retain pending state for disconnect or next boot, but stop retrying. */
        LOG_WRN("Failed to update advertising name (err %d)", err);
    }
}

static void stage_advertising_name(const char *name)
{
    const char *resolved = (name != NULL && name[0] != '\0') ? name : CONFIG_BT_DEVICE_NAME;
    k_spinlock_key_t key = k_spin_lock(&adv_name_lock);
    strncpy(adv_device_name, resolved, sizeof(adv_device_name) - 1);
    adv_device_name[sizeof(adv_device_name) - 1] = '\0';
    ++adv_name_generation;
    adv_name_pending = true;
    adv_name_retries = 0;
    k_spin_unlock(&adv_name_lock, key);
}

static void update_advertising_name(const char *name)
{
    stage_advertising_name(name);
    /* HCI calls must run outside Bluetooth RX. A running work item may be
     * resubmitted, so an update arriving during HCI is applied on the next run. */
    k_work_reschedule(&adv_name_update_work, K_NO_WAIT);
}

static void advertising_name_disconnected(void)
{
    k_spinlock_key_t key = k_spin_lock(&adv_name_lock);
    bool pending = adv_name_pending;
    if (pending) {
        adv_name_retries = 0;
    }
    k_spin_unlock(&adv_name_lock, key);
    if (pending) {
        /* RX callback precedes host advertising resume. Defer HCI and allow a
         * bounded retry window if resume has not completed on the first run. */
        k_work_reschedule(&adv_name_update_work, K_MSEC(ADV_NAME_RETRY_MS));
    }
}

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

#ifdef CONFIG_OMI_ENABLE_SPEAKER
static ssize_t audio_data_write_handler(struct bt_conn *conn,
                                        const struct bt_gatt_attr *attr,
                                        const void *buf,
                                        uint16_t len,
                                        uint16_t offset,
                                        uint8_t flags)
{
    uint16_t amount = 400;
    bt_gatt_notify(conn, attr, &amount, sizeof(amount));
    amount = speak(len, buf);
    return len;
}
#endif

static ssize_t settings_dim_ratio_write_handler(struct bt_conn *conn,
                                                const struct bt_gatt_attr *attr,
                                                const void *buf,
                                                uint16_t len,
                                                uint16_t offset,
                                                uint8_t flags)
{
    if (offset != 0) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
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

static ssize_t settings_mute_write_handler(struct bt_conn *conn,
                                           const struct bt_gatt_attr *attr,
                                           const void *buf,
                                           uint16_t len,
                                           uint16_t offset,
                                           uint8_t flags)
{
    return capture_mute_gatt_write(buf, len, offset);
}

static ssize_t settings_mute_read_handler(struct bt_conn *conn,
                                          const struct bt_gatt_attr *attr,
                                          void *buf,
                                          uint16_t len,
                                          uint16_t offset)
{
    uint8_t current_muted = capture_mute_is_set() ? 1U : 0U;
    LOG_INF("Reading capture mute: %u", current_muted);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &current_muted, sizeof(current_muted));
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

static ssize_t settings_device_name_write_handler(struct bt_conn *conn,
                                                  const struct bt_gatt_attr *attr,
                                                  const void *buf,
                                                  uint16_t len,
                                                  uint16_t offset,
                                                  uint8_t flags)
{
    if (offset != 0) {
        LOG_WRN("Invalid offset for device name write: %u", offset);
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }

    if (len > MAX_DEVICE_NAME_PAYLOAD_LEN) {
        LOG_WRN("Invalid length for device name write: %u (max %u)", len, MAX_DEVICE_NAME_PAYLOAD_LEN);
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    if (len > 0 && memchr(buf, '\0', len) != NULL) {
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }
    char new_name[MAX_DEVICE_NAME_LEN] = {0};
    if (len > 0) {
        memcpy(new_name, buf, len);
        new_name[len] = '\0';
    }

    LOG_INF("Received new device name: %s", new_name);
    int err = app_settings_save_device_name(new_name);
    if (err) {
        LOG_ERR("Failed to save device name setting: %d", err);
        return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
    }

    update_advertising_name(new_name);

    return len;
}

static ssize_t settings_device_name_read_handler(struct bt_conn *conn,
                                                 const struct bt_gatt_attr *attr,
                                                 void *buf,
                                                 uint16_t len,
                                                 uint16_t offset)
{
    const char *name = app_settings_get_device_name();
    if (name == NULL || strlen(name) == 0) {
        name = "";
    }
    LOG_INF("Reading device name: %s", name);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, name, strlen(name));
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
    features |= OMI_FEATURE_DEVICE_NAME;
    // Persistent capture mute (NVS + BLE). Always present on this firmware.
    features |= OMI_FEATURE_CAPTURE_MUTE;
    features |= OMI_FEATURE_POWER_CONTROL;

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
#define BATTERY_REFRESH_INTERVAL_CONNECTED 5000     // 5 seconds
#define BATTERY_REFRESH_INTERVAL_DISCONNECTED 10000 // 10 seconds
uint8_t battery_percentage = 0;
static struct battery_critical_guard battery_critical;
static int8_t charging_status_last_notified = -1;
void broadcast_battery_level(struct k_work *work_item);

static int notify_charging_status(struct bt_conn *conn, bool force_notify)
{
    if (conn == NULL) {
        return -ENOTCONN;
    }

    if (!bt_gatt_is_subscribed(conn, &settings_service.attrs[6], BT_GATT_CCC_NOTIFY)) {
        return 0;
    }

    uint8_t charging_status = is_charging ? 1U : 0U;
    if (!force_notify && charging_status_last_notified == (int8_t) charging_status) {
        return 0;
    }

    int err = bt_gatt_notify(conn, &settings_service.attrs[6], &charging_status, sizeof(charging_status));
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
    (void) work_item;
    uint16_t battery_millivolt;
    uint32_t next_refresh_interval = (is_connected && current_connection != NULL)
                                         ? BATTERY_REFRESH_INTERVAL_CONNECTED
                                         : BATTERY_REFRESH_INTERVAL_DISCONNECTED;

    int battery_err = battery_get_millivolt(&battery_millivolt);
    struct battery_diagnostics battery = {.charge_pin = UINT8_MAX};
    if (battery_err == 0) {
        battery_get_diagnostics(&battery);
        omi_diagnostics_set_battery_mv(battery.millivolts);
    } else {
        omi_diagnostics_set_battery_mv(UINT16_MAX);
    }
    if (battery_err == 0 && battery_get_percentage(&battery_percentage, battery_millivolt) == 0) {

        LOG_PRINTK("Battery at %d mV (capacity %d%%)\n", battery_millivolt, battery_percentage);

        if (is_connected && current_connection != NULL) {
            /* Report battery even during an SD sync. It's 1 byte at most every few
             * seconds and AUDIO_TX_RESERVED_SLOTS keeps TX buffers free for
             * non-audio notifications, so it can't starve the sync/audio stream.
             * The old storage_transfer_active() early-return meant the app never
             * got a battery update for the whole (often long) duration of a sync. */
            (void) notify_charging_status(current_connection, false);
        }
        // Keep the readable BAS byte current even when there is no connection.
        int err = bt_bas_set_battery_level(battery_percentage);
        if (err) {
            LOG_ERR("Error updating battery level: %d", err);
        }
        /* Debounced and never while charging (3.0.24): one sag below the
         * threshold, or a reading on the charger, no longer powers off. An
         * unreadable charger pin (charge_pin unknown) counts as not charging,
         * so a stale "charging" can never suppress protection indefinitely. */
        bool charging = battery.charge_pin == 1U;
        if (battery_critical_should_shutdown(&battery_critical, battery_millivolt, charging)) {
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
    diagnostics_reset_read_cache(conn);

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
    struct bt_conn *new_conn = bt_conn_ref(conn);
    {
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        current_connection = new_conn;
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
        storage_connection_changed();
#endif
        k_spin_unlock(&connection_lock, key);
    }
    uint16_t mtu = bt_gatt_get_mtu(conn);
    current_mtu = mtu;

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    /* Kick the SD remount immediately (it may be off from offline AAD sleep) so
     * it is mounted well before the app fires its one-shot sync command. */
    sd_request_power(true);
#endif

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
    /* SD power-on was already requested at the top of this handler. */
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
    diagnostics_reset_read_cache(conn);

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

    struct bt_conn *old_conn;
    {
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        old_conn = current_connection;
        current_connection = NULL;
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
        storage_connection_changed();
#endif
        k_spin_unlock(&connection_lock, key);
    }
    if (old_conn != NULL) {
        bt_conn_unref(old_conn);
    }

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    /* No phone left to sync: if the mic is idle in AAD sleep, drop SD power again
     * (it was kept on for the connection). */
    if (mic_in_aad_sleep()) {
        sd_request_power(false);
    }
#endif

    LOG_INF("Transport disconnected");
    current_mtu = 0;
    charging_status_last_notified = -1;

    // Reset the audio TX throttle semaphore so the pusher thread is not
    // left blocked forever if it was waiting for a slot when the connection dropped.
    k_sem_init(&audio_tx_sem,
               CONFIG_BT_CONN_TX_MAX - AUDIO_TX_RESERVED_SLOTS,
               CONFIG_BT_CONN_TX_MAX - AUDIO_TX_RESERVED_SLOTS);
    /* Start the retry window after callback cleanup, just before host resume. */
    advertising_name_disconnected();
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

#define PHY_UPDATE_RETRY_COUNT 3
#define PHY_UPDATE_RETRY_DELAY_MS 150
#define MTU_UPDATE_RETRY_COUNT 3
#define MTU_UPDATE_RETRY_DELAY_MS 120
#define CONN_PARAM_RETRY_COUNT 3
#define CONN_PARAM_RETRY_DELAY_MS 300

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
            LOG_WRN("bt_conn_le_param_update() failed (err %d), retry %d/%d", err, attempt, CONN_PARAM_RETRY_COUNT);
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
            LOG_WRN("bt_conn_le_phy_update() failed (err %d), retry %d/%d", err, attempt, PHY_UPDATE_RETRY_COUNT);
            k_sleep(K_MSEC(PHY_UPDATE_RETRY_DELAY_MS));
        }
    }

    LOG_ERR("bt_conn_le_phy_update() failed after %d retries (last err %d)", PHY_UPDATE_RETRY_COUNT, err);
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
    LOG_WRN("MTU still %u, re-requesting exchange (%u/%u)", mtu, mtu_recheck_attempts, MTU_RECHECK_MAX_ATTEMPTS);
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
            LOG_WRN("bt_gatt_exchange_mtu() busy (err %d), retry %d/%d", err, attempt, MTU_UPDATE_RETRY_COUNT);
            k_sleep(K_MSEC(MTU_UPDATE_RETRY_DELAY_MS));
            continue;
        }

        LOG_ERR("bt_gatt_exchange_mtu() failed (err %d)", err);
        return;
    }

    LOG_ERR("bt_gatt_exchange_mtu() failed after retries (last err %d)", err);
}

static void log_local_ble_addresses(void)
{
    bt_addr_le_t addrs[CONFIG_BT_ID_MAX];
    size_t count = CONFIG_BT_ID_MAX;

    bt_id_get(addrs, &count);

    if (count == 0U) {
        LOG_WRN("No local BLE identity address found");
        printk("BLE_ADDR: unavailable (count=0)\n");
        return;
    }

    for (size_t i = 0; i < count; i++) {
        char addr[BT_ADDR_LE_STR_LEN];

        bt_addr_le_to_str(&addrs[i], addr, sizeof(addr));
        LOG_INF("BLE identity[%u]: %s", (unsigned int) i, addr);
        printk("BLE_ADDR[%u]: %s\n", (unsigned int) i, addr);
    }
}

static int ensure_local_ble_identity(void)
{
#if defined(CONFIG_BT_SETTINGS)
    /* Recovery uses unencrypted SMP; do not enter a broken settings/bond path. */
    if (!safe_mode_active()) {
        int err = settings_load();
        if (err && err != -ENOENT) {
            LOG_ERR("Failed to load BT settings (err %d)", err);
            return err;
        }
    }
#endif

    bt_addr_le_t addrs[CONFIG_BT_ID_MAX];
    size_t count = CONFIG_BT_ID_MAX;

    bt_id_get(addrs, &count);
    if (count > 0U) {
        return 0;
    }

    int id = bt_id_create(NULL, NULL);
    if (id < 0) {
        LOG_ERR("Failed to create local BLE identity (err %d)", id);
        return id;
    }

    LOG_INF("Created local BLE identity %d", id);
    return 0;
}

//
// Ring Buffer
//

#define NET_BUFFER_HEADER_SIZE 3
#define ATT_NOTIFICATION_HEADER_SIZE 3 // ATT opcode (1 byte) and attribute handle (2 bytes)
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
        omi_diagnostics_inc_ble_tx_drop();
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
        omi_diagnostics_inc_ble_tx_drop();
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

// Shared TX-slot reservation. The storage-sync path takes/releases the same
// semaphore as the audio pusher, so audio + sync together never consume the
// last AUDIO_TX_RESERVED_SLOTS buffers -> they stay free for short control
// notifications (battery/charging/status), which were otherwise starved (-ENOMEM)
// during a sync.
int transport_bulk_tx_acquire(k_timeout_t timeout)
{
    return k_sem_take(&audio_tx_sem, timeout);
}

void transport_bulk_tx_release(void)
{
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
        uint32_t packet_size =
            MIN(current_mtu - ATT_NOTIFICATION_HEADER_SIZE - NET_BUFFER_HEADER_SIZE, tx_buffer_size - offset);

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
            omi_diagnostics_inc_ble_tx_drop();
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

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
static uint8_t storage_temp_data[MAX_WRITE_SIZE];
static uint8_t storage_record_buf[MAX_WRITE_SIZE];
static omi_live_pack_t live_pack;
static bool live_pack_ready;
static int64_t last_pack_activity_ms;
static uint32_t last_pack_session;

atomic_t omi_live_persist_records_queued = ATOMIC_INIT(0);
atomic_t omi_live_persist_records_dropped = ATOMIC_INIT(0);
atomic_t omi_live_persist_frames_dropped = ATOMIC_INIT(0);

static void storage_pack_init(void)
{
    if (!live_pack_ready) {
        omi_live_pack_init(&live_pack, storage_temp_data, MAX_WRITE_SIZE);
        live_pack_ready = true;
    }
}

static void storage_submit_record(uint32_t session, uint16_t boundary)
{
    uint32_t wrote = sd_ring_write_record(storage_record_buf, MAX_WRITE_SIZE, session, boundary);
    if (wrote == 0U) {
        atomic_inc(&omi_live_persist_records_dropped);
        live_pack.invalidate_next = true;
        if (live_pack.offset > 0U) {
            live_pack.record_session = 0U;
        }
        static int64_t last_drop_log_ms;
        int64_t now = k_uptime_get();
        if (now - last_drop_log_ms > 2000) {
            LOG_WRN("ring record dropped (queue unavailable), dropped=%ld",
                    (long) atomic_get(&omi_live_persist_records_dropped));
            last_drop_log_ms = now;
        }
    } else {
        atomic_inc(&omi_live_persist_records_queued);
    }
}

static void storage_pack_drain(void)
{
    uint32_t session;
    uint16_t boundary;
    if (omi_live_pack_flush(&live_pack, storage_record_buf, &session, &boundary)) {
        storage_submit_record(session, boundary);
    }
}

static void write_to_storage(uint32_t session, uint16_t boundary)
{
    storage_pack_init();

    uint32_t record_session;
    uint16_t record_boundary;
    if (omi_live_pack_frame(&live_pack,
                            tx_buffer + RING_BUFFER_HEADER_SIZE,
                            (uint16_t) tx_buffer_size,
                            session,
                            boundary,
                            storage_record_buf,
                            &record_session,
                            &record_boundary)) {
        storage_submit_record(record_session, record_boundary);
    }

    last_pack_activity_ms = k_uptime_get();
    last_pack_session = session;

#ifdef CONFIG_OMI_ENABLE_MONITOR
    monitor_inc_storage_write();
#endif
}
#endif

#define MAX_FILES 10
#define MAX_AUDIO_FILE_SIZE 300000

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

#define STORAGE_PACK_IDLE_FLUSH_MS 1000

void pusher(void)
{
    k_msleep(500);
    while (!atomic_get(&pusher_stop_flag)) {
        k_sem_take(&tx_queue_sem, K_MSEC(200));
        if (atomic_get(&pusher_stop_flag)) {
            break;
        }

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
        if (live_pack_ready && live_pack.offset > 0U &&
            (k_uptime_get() - last_pack_activity_ms) >= STORAGE_PACK_IDLE_FLUSH_MS) {
            storage_pack_drain();
        }
#endif

        while (read_from_tx_queue()) {
            struct bt_conn *conn = get_current_connection_ref();
            bool is_subscribed = false;
            if (conn && current_mtu >= MINIMAL_PACKET_SIZE) {
                is_subscribed = bt_gatt_is_subscribed(conn, &audio_service.attrs[1], BT_GATT_CCC_NOTIFY);
            }

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
            uint32_t session_before = storage_live_session();
#endif

            bool sent = false;
            /* Issue #5054: a mute also stops frames already queued from reaching the phone. */
            if (conn && is_subscribed && capture_mute_should_capture()) {
                sent = push_to_gatt(conn);
            }

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
            uint32_t live_session = storage_live_session();
            if (live_session != last_pack_session) {
                storage_pack_init();
                storage_pack_drain();
                last_pack_session = live_session;
            }

            /* Issue #5054: muted packets are dropped, not stored, even offline. */
            if (!capture_mute_should_capture()) {
                if (conn) {
                    bt_conn_unref(conn);
                }
                continue;
            }

            if (conn && is_subscribed) {
                if (live_session != 0U) {
                    uint32_t frame_session = (sent && session_before == live_session) ? live_session : 0U;
                    write_to_storage(frame_session, packet_next_index);
                } else if (session_before != 0U) {
                    write_to_storage(0U, packet_next_index);
                } else if (!sent) {
                    live_pack.invalidate_next = true;
                }
            } else {
                if (is_sd_on()) {
                    storage_full_warned = false;
                    write_to_storage(0U, packet_next_index);
                } else {
                    live_pack.invalidate_next = true;
                    atomic_inc(&omi_live_persist_frames_dropped);
                    if (!storage_full_warned) {
                        LOG_WRN("Offline storage unavailable");
                        storage_full_warned = true;
                    }
                }
            }
#else
            if (conn && !is_subscribed) {
                k_sleep(K_MSEC(10));
            }
#endif

            if (conn) {
                bt_conn_unref(conn);
            }
        }
    }

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    {
        uint32_t drain_session = storage_live_session();
        struct bt_conn *conn = get_current_connection_ref();
        bool drain_subscribed = false;
        if (conn && current_mtu >= MINIMAL_PACKET_SIZE) {
            drain_subscribed = bt_gatt_is_subscribed(conn, &audio_service.attrs[1], BT_GATT_CCC_NOTIFY);
        }
        if (conn) {
            bt_conn_unref(conn);
        }
        bool persist_tail = (drain_session != 0U) || !drain_subscribed;
        while (persist_tail && read_from_tx_queue()) {
            write_to_storage(0U, packet_next_index);
        }
    }
    if (live_pack_ready) {
        storage_pack_drain();
    }
#endif
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
    struct bt_conn *old_conn;
    {
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        old_conn = current_connection;
        current_connection = NULL;
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
        storage_is_on = false;
        storage_connection_changed();
#endif
        k_spin_unlock(&connection_lock, key);
    }
    if (old_conn != NULL) {
        bt_conn_disconnect(old_conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        bt_conn_unref(old_conn);
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

    return 0;
}

int transport_start_safe(void)
{
    int err;
    bt_conn_cb_register(&recovery_callbacks);
#ifdef CONFIG_OMI_ENABLE_RFSW_CTRL
    err = gpio_pin_configure_dt(&rfsw_en, GPIO_OUTPUT_ACTIVE | NRF_GPIO_DRIVE_S0H1);
    if (err) {
        return err;
    }
#endif
    /* No application connection callbacks: they touch SD/audio and start work.
     * SMP and DIS register themselves; leave external NOR and SPI3 awake.
     */
    err = bt_enable(NULL);
    if (err) {
        return err;
    }
    err = ensure_local_ble_identity();
    if (err) {
        return err;
    }
    log_local_ble_addresses();
    err = bt_gatt_service_register(&safe_diagnostics_service);
    if (err) {
        return err;
    }
    const struct bt_data bt_sd[] = {
        BT_DATA_BYTES(BT_DATA_UUID16_ALL, BT_UUID_16_ENCODE(BT_UUID_DIS_VAL)),
        BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
    };
    err = bt_le_adv_start(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_CONNECTABLE, 1600, 3200, NULL),
                          bt_ad,
                          ARRAY_SIZE(bt_ad),
                          bt_sd,
                          ARRAY_SIZE(bt_sd));
    advertising_started = !err;
    return err;
}

// periodic advertising
int transport_start()
{
    int err = 0;

    k_thread_start(power_off_thread);

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

    err = ensure_local_ble_identity();
    if (err) {
        LOG_WRN("Continuing without confirmed BLE identity (err %d)", err);
    }

    // Production-line helper: emit local BLE addresses on UART for fixture parsing.
    log_local_ble_addresses();

    // After settings_load(): expose the immutable per-unit ID as DIS serial (0x2A25).
    err = unit_id_publish();
    if (err) {
        LOG_WRN("Continuing without DIS serial number (err %d)", err);
    }

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
    k_work_init_delayable(&adv_name_update_work, adv_name_update_work_handler);
    bt_gatt_service_register(&audio_service);
    bt_gatt_service_register(&settings_service);
    bt_gatt_service_register(&features_service);
    bt_gatt_service_register(&time_sync_service);

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    // Register storage service for offline audio
    memset(storage_temp_data, 0, OPUS_PADDED_LENGTH * 4);
    bt_gatt_service_register(&storage_service);
#endif
    bt_gatt_service_register(&diagnostics_service);
    stage_advertising_name(app_settings_get_device_name());
    err = apply_advertising_name(true);
    if (err) {
        LOG_ERR("Transport advertising failed to start (err %d), continuing without BLE", err);
        // Non-fatal: continue with pusher and ring buffer so offline recording works
    } else {
        advertising_started = true;
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

struct bt_conn *get_current_connection_ref(void)
{
    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    struct bt_conn *conn = (current_connection != NULL) ? bt_conn_ref(current_connection) : NULL;
    k_spin_unlock(&connection_lock, key);
    return conn;
}

int broadcast_audio_packets(uint8_t *buffer, size_t size)
{
    if (!write_to_tx_queue(buffer, size)) {
        return -1;
    }
    return 0;
}
