/* Device-boundary doubles, compiled against the production seam declarations.
 * Every synthetic milestone is labelled SIM. No device IO or BLE stack.
 * Watchdog, power-off, reset register and pins live in sim_power.c.
 */
#include <string.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device.h>

#include "imu.h"
#include "lib/core/battery_guard.h"
#include "lib/core/button.h"
#include "lib/core/capture_mute.h"
#include "lib/core/codec.h"
#include "lib/core/haptic.h"
#include "lib/core/led.h"
#include "lib/core/lib/battery/battery.h"
#include "lib/core/mic.h"
#include "lib/core/sd_card.h"
#include "lib/core/storage.h"
#include "lib/core/transport.h"
#include "safe_mode.h"
#include "safe_mode_sim_mgmt.h"
#include "sim_hw.h"
#include "sim_plan.h"
#include "spi_flash.h"

LOG_MODULE_REGISTER(sim_stubs, CONFIG_LOG_DEFAULT_LEVEL);

uint8_t battery_percentage = 75;
static mix_handler mic_callback;
static codec_callback encoded_callback;

int flash_off(void)
{
    return 0;
}
int led_start(void)
{
    return 0;
}
void set_led_red(bool on)
{
    ARG_UNUSED(on);
}
void set_led_green(bool on)
{
    ARG_UNUSED(on);
}
void set_led_blue(bool on)
{
    ARG_UNUSED(on);
}
void set_led_pwm(led_color_t color, uint8_t level)
{
    ARG_UNUSED(color);
    ARG_UNUSED(level);
}
void led_off(void) {}
int lsm6dsl_time_boot_adjust_rtc(void)
{
    return 0;
}
void lsm6dsl_time_prepare_for_system_off(void) {}

#ifdef CONFIG_OMI_ENABLE_HAPTIC
int haptic_init(void)
{
    return 0;
}
void play_haptic_milli(uint32_t duration)
{
    ARG_UNUSED(duration);
}
void haptic_off(void) {}
#endif

/* ---- charger / battery ------------------------------------------------ */

extern bool is_charging;
static const struct gpio_dt_spec bat_chg = GPIO_DT_SPEC_GET(DT_NODELABEL(bat_chg_pin), gpios);
static struct gpio_callback bat_chg_cb;

/* Mirrors battery.c: the charger status pin reads 0 while the charge IC is active. */
static void charger_changed(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    ARG_UNUSED(dev);
    ARG_UNUSED(cb);
    ARG_UNUSED(pins);
    is_charging = gpio_pin_get_dt(&bat_chg) == 0;
}

/* SIM stand-in for transport.c's broadcast_battery_level(): same cadence
 * (5 s connected, 10 s otherwise), the same -16 mV charging correction as
 * battery_get_millivolt(), and the real shutdown policy and turnoff_all(). */
static struct battery_critical_guard battery_critical;
static void battery_sample(struct k_work *work)
{
    uint16_t mv = (uint16_t) omi_sim_battery_mv();
    if (is_charging && mv > 16) {
        mv -= 16;
    }
    printk("SIM: battery sample %u mV charging=%d\n", mv, is_charging);
    if (battery_critical_should_shutdown(&battery_critical, mv, is_charging)) {
        LOG_WRN("Battery critical level reached (%d mV). Initiating shutdown.", mv);
        turnoff_all();
    }
    k_work_reschedule(k_work_delayable_from_work(work), K_MSEC(omi_sim_connected() ? 5000 : 10000));
}
K_WORK_DELAYABLE_DEFINE(battery_work, battery_sample);

int battery_init(void)
{
    k_work_schedule(&battery_work, K_MSEC(10000));
    (void) gpio_pin_configure_dt(&bat_chg, GPIO_INPUT);
    (void) gpio_pin_interrupt_configure_dt(&bat_chg, GPIO_INT_EDGE_BOTH);
    gpio_init_callback(&bat_chg_cb, charger_changed, BIT(bat_chg.pin));
    (void) gpio_add_callback(bat_chg.port, &bat_chg_cb);
    is_charging = gpio_pin_get_dt(&bat_chg) == 0;
    LOG_INF("SIM: battery stub reports 75%% (charging=%d)", is_charging);
    return 0;
}
int battery_charge_start(void)
{
    return 0;
}

/* ---- SD / storage ----------------------------------------------------- */
/* The real raw-ring driver (sd_card.c) runs over the simulated card in
 * sim_sd.c. Only the storage service (BLE sync) and diagnostics are stubbed. */

unsigned int omi_sim_sd_init_calls(void);
static bool sd_paused;

/* --wrap: observe the pause bit capture_mute.c drives, then apply it. */
void __real_sd_write_pause(bool pause);
void __wrap_sd_write_pause(bool pause)
{
    sd_paused = pause;
    printk("SIM: sd_write_pause(%d)\n", pause);
    __real_sd_write_pause(pause);
}
bool omi_sim_sd_paused(void)
{
    return sd_paused;
}
unsigned int omi_sim_sd_mount_attempts(void)
{
    return omi_sim_sd_init_calls();
}
bool omi_sim_sd_ready(void)
{
    return sd_is_ready();
}
int storage_init(void)
{
    LOG_INF("SIM: storage init stub (no storage worker)");
    return 0;
}
void storage_queue_live_mark(uint64_t ring_id, uint64_t ring_seq, uint16_t live_index, uint32_t session)
{
    ARG_UNUSED(ring_id);
    ARG_UNUSED(ring_seq);
    ARG_UNUSED(live_index);
    ARG_UNUSED(session);
}
void omi_diagnostics_inc_storage_error(void) {}

/* CONFIG_PM_DEVICE is off here; the SD slot has no power states to model. */
int pm_device_action_run(const struct device *dev, enum pm_device_action action)
{
    ARG_UNUSED(dev);
    ARG_UNUSED(action);
    return -ENOSYS;
}

/* SIM audio pusher: one 440-byte packet every 100 ms while offline, through
 * the same capture gate transport.c's pusher uses before storing audio. */
static unsigned int sd_written, sd_dropped, sd_gated;
unsigned int omi_sim_sd_written(void)
{
    return sd_written;
}
unsigned int omi_sim_sd_dropped(void)
{
    return sd_dropped;
}
unsigned int omi_sim_sd_gated(void)
{
    return sd_gated;
}
extern bool is_off;
static void pusher(void *a, void *b, void *c)
{
    ARG_UNUSED(a);
    ARG_UNUSED(b);
    ARG_UNUSED(c);
    static uint8_t packet[MAX_WRITE_SIZE];
    while (!omi_sim_transport_up()) {
        k_msleep(100);
    }
    for (uint32_t n = 0;; ++n) {
        k_msleep(100);
        if (is_off || omi_sim_connected()) {
            continue;
        }
        if (!capture_mute_should_capture()) {
            sd_gated++;
            continue;
        }
        memset(packet, (int) (n & 0xff), sizeof(packet));
        if (write_to_file(packet, sizeof(packet)) == sizeof(packet)) {
            sd_written++;
        } else {
            sd_dropped++;
        }
    }
}
K_THREAD_DEFINE(sim_pusher, 2048, pusher, NULL, NULL, NULL, 8, 0, 0);

/* ---- transport / BLE -------------------------------------------------- */

/* Opaque non-NULL token: button.c only passes it back to the GATT stubs. */
static uint8_t fake_conn;
struct bt_conn *get_current_connection(void)
{
    return omi_sim_connected() ? (struct bt_conn *) &fake_conn : NULL;
}
static bool transport_up;
bool omi_sim_transport_up(void)
{
    return transport_up;
}
int transport_start(void)
{
    transport_up = true;
    LOG_INF("SIM: Transport bluetooth initialized (stub; BLE disabled)");
    LOG_INF("SIM: Advertising successfully started (stub; no radio)");
    return 0;
}
int transport_off(void)
{
    printk("SIM: transport_off\n");
    return 0;
}
bool transport_advertising_started(void)
{
    return true;
}
int transport_start_safe(void)
{
    return 0;
}
int broadcast_audio_packets(uint8_t *buffer, size_t size)
{
    ARG_UNUSED(buffer);
    ARG_UNUSED(size);
    return -ENOTSUP;
}

int bt_gatt_notify_cb(struct bt_conn *conn, struct bt_gatt_notify_params *params)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(params);
    printk("SIM: GATT notify\n");
    return 0;
}
int bt_gatt_service_register(struct bt_gatt_service *svc)
{
    ARG_UNUSED(svc);
    return 0;
}
ssize_t bt_gatt_attr_read(struct bt_conn *conn,
                          const struct bt_gatt_attr *attr,
                          void *buf,
                          uint16_t buf_len,
                          uint16_t offset,
                          const void *value,
                          uint16_t value_len)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(buf);
    ARG_UNUSED(buf_len);
    ARG_UNUSED(offset);
    ARG_UNUSED(value);
    return value_len;
}
ssize_t bt_gatt_attr_read_service(struct bt_conn *conn,
                                  const struct bt_gatt_attr *attr,
                                  void *buf,
                                  uint16_t len,
                                  uint16_t offset)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(buf);
    ARG_UNUSED(len);
    ARG_UNUSED(offset);
    return 0;
}
ssize_t
bt_gatt_attr_read_chrc(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read_service(conn, attr, buf, len, offset);
}
ssize_t
bt_gatt_attr_read_ccc(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read_service(conn, attr, buf, len, offset);
}
ssize_t bt_gatt_attr_write_ccc(struct bt_conn *conn,
                               const struct bt_gatt_attr *attr,
                               const void *buf,
                               uint16_t len,
                               uint16_t offset,
                               uint8_t flags)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(buf);
    ARG_UNUSED(offset);
    ARG_UNUSED(flags);
    return len;
}

/* ---- audio ------------------------------------------------------------ */

void set_codec_callback(codec_callback callback)
{
    encoded_callback = callback;
}
int codec_start(void)
{
    __ASSERT(encoded_callback != NULL, "main must register codec callback first");
    LOG_INF("SIM: codec init stub (ARM Opus not linked)");
    return 0;
}
int codec_receive_pcm(int16_t *data, size_t len)
{
    ARG_UNUSED(data);
    ARG_UNUSED(len);
    return -ENOTSUP;
}
void set_mic_callback(mix_handler callback)
{
    mic_callback = callback;
}
int mic_start(void)
{
    __ASSERT(mic_callback != NULL, "main must register microphone callback first");
    LOG_INF("SIM: Microphone started (stub; no PCM generated)");
    return 0;
}
void mic_off(void)
{
    printk("SIM: mic_off\n");
}

/* ---- mcumgr seam ------------------------------------------------------ */

static struct mgmt_callback *sim_dfu_callback;
void mgmt_callback_register(struct mgmt_callback *callback)
{
    sim_dfu_callback = callback;
}

void omi_sim_dfu(int op)
{
    static const char *const names[] = {"?", "chunk image 0", "chunk image 1", "chunk net area", "stopped", "pending"};
    if (!sim_dfu_callback) {
        printk("SIM: dfu event dropped (no mcumgr callback)\n");
        return;
    }
    struct img_mgmt_upload_req req = {.image = op == OMI_SIM_DFU_CHUNK_IMAGE1 ? 1 : 0};
    struct img_mgmt_upload_action action = {
        .area_id = op == OMI_SIM_DFU_CHUNK_APP ? FIXED_PARTITION_ID(slot1_partition) : -1,
    };
    struct img_mgmt_upload_check check = {.req = &req, .action = &action};
    int32_t rc = 0;
    bool abort_more = false;
    enum mgmt_cb_return ret = MGMT_CB_OK;
    switch (op) {
    case OMI_SIM_DFU_CHUNK_APP:
    case OMI_SIM_DFU_CHUNK_IMAGE1:
    case OMI_SIM_DFU_CHUNK_NET:
        ret = sim_dfu_callback->callback(
            MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK, MGMT_CB_OK, &rc, NULL, &abort_more, &check, sizeof(check));
        break;
    case OMI_SIM_DFU_STOPPED:
        ret = sim_dfu_callback->callback(MGMT_EVT_OP_IMG_MGMT_DFU_STOPPED, MGMT_CB_OK, NULL, NULL, NULL, NULL, 0);
        break;
    case OMI_SIM_DFU_PENDING:
        ret = sim_dfu_callback->callback(MGMT_EVT_OP_IMG_MGMT_DFU_PENDING, MGMT_CB_OK, NULL, NULL, NULL, NULL, 0);
        break;
    default:
        printk("SIM: unknown dfu op %d\n", op);
        return;
    }
    printk("SIM: dfu %s -> %s (rc=%d)\n", names[op], ret == MGMT_CB_OK ? "accepted" : "rejected", (int) rc);
}

#ifdef CONFIG_OMI_SIM_FINISH_DFU
/* Deliver a synthetic completed image-0 upload a few seconds into SAFE. */
static void finish_dfu(struct k_work *work)
{
    ARG_UNUSED(work);
    if (!sim_dfu_callback) {
        return;
    }
    if (!safe_mode_active()) {
        /* Manual entry samples the button for up to 10 s before SAFE starts. */
        k_work_schedule(k_work_delayable_from_work(work), K_SECONDS(1));
        return;
    }
    struct img_mgmt_upload_req req = {.image = 0};
    struct img_mgmt_upload_action action = {.area_id = FIXED_PARTITION_ID(slot1_partition)};
    struct img_mgmt_upload_check check = {.req = &req, .action = &action};
    int32_t rc = 0;
    bool abort_more = false;
    sim_dfu_callback->callback(
        MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK, MGMT_CB_OK, &rc, NULL, &abort_more, &check, sizeof(check));
    sim_dfu_callback->callback(MGMT_EVT_OP_IMG_MGMT_DFU_PENDING, MGMT_CB_OK, NULL, NULL, NULL, NULL, 0);
    sim_dfu_callback = NULL;
}
K_WORK_DELAYABLE_DEFINE(finish_dfu_work, finish_dfu);
static int arm_finish_dfu(void)
{
    k_work_schedule(&finish_dfu_work, K_SECONDS(3));
    return 0;
}
SYS_INIT(arm_finish_dfu, APPLICATION, 99);
#endif
