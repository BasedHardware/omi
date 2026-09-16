// Pendant HID dictation prototype — Zephyr glue.
//
// Owns the GATT control plane (dictation service 19B10040), the standard BLE
// HID keyboard service (NCS HIDS), and the typing engine that drains the
// validated session buffer produced by hid_dictation_core.c.
//
// Safety contract (see test/host and HID_DICTATION_PROTOTYPE.md):
//   - one key pressed at a time, always followed by a zero (release) report;
//   - every exit path (done, cancel, error, timeout, disconnect) sends a
//     release report if a link is still up, then forgets the session;
//   - nothing persists across reconnects: enable state is RAM-only and the
//     session buffer is dropped at disconnect (no replay).

#include "hid_dictation.h"

#include <bluetooth/services/hids.h>
#include <errno.h>
#include <string.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>

LOG_MODULE_REGISTER(hid_dictation, CONFIG_LOG_DEFAULT_LEVEL);

#define DICTATION_INPUT_REPORT_LEN 8 // [modifier][reserved][key1..key6]

// Typing pace: one report (press or release) per interval. Two intervals per
// character keeps every press/release pair inside its own connection event.
#define DICTATION_KEY_INTERVAL_MS CONFIG_OMI_HID_DICTATION_KEY_INTERVAL_MS
#define DICTATION_FRAME_TIMEOUT_MS CONFIG_OMI_HID_DICTATION_FRAME_TIMEOUT_MS
#define DICTATION_TYPE_BUDGET_MS CONFIG_OMI_HID_DICTATION_TYPE_BUDGET_MS

static uint8_t dictation_text[CONFIG_OMI_HID_DICTATION_MAX_TEXT_LEN];
static struct hid_dictation_limits dictation_limits = {
    .max_text_len = sizeof(dictation_text),
};
static struct hid_dictation_ctx dictation_ctx;

// Opt-in state. RAM-only by design: a power cycle returns the pendant to
// stock behavior, which is also the documented recovery path.
static bool hid_wanted;     // requested by the app
static bool hid_registered; // HIDS currently in the GATT table

static struct bt_conn *conn_ref; // last connection handed to on_connected

// --- HIDS instance (standard HID over GATT keyboard) ---

BT_HIDS_DEF(hids_obj,

            1, // boot keyboard output report (LEDs)
            DICTATION_INPUT_REPORT_LEN);
static struct bt_gatt_service dictation_service;

static void hids_pm_evt_handler(enum bt_hids_pm_evt evt, struct bt_conn *conn)
{
    ARG_UNUSED(evt);
    ARG_UNUSED(conn);
}

static void hids_inp_rep_handler(enum bt_hids_notify_evt evt)
{
    // CCC events for the report input characteristic (the HID host subscribing).
    if (evt == BT_HIDS_CCCD_EVT_NOTIFY_ENABLED) {
        LOG_INF("HID host subscribed to input reports");
    } else {
        LOG_INF("HID host unsubscribed from input reports");
    }
}

static int hids_register(void)
{
    if (hid_registered) {
        return 0;
    }

    static const uint8_t report_map[] = {
        0x05, 0x01, // Usage Page (Generic Desktop)
        0x09, 0x06, // Usage (Keyboard)
        0xA1, 0x01, // Collection (Application)
        0x05, 0x07, //   Usage Page (Key Codes)
        0x19, 0xe0, //   Usage Minimum (224)
        0x29, 0xe7, //   Usage Maximum (231)
        0x15, 0x00, //   Logical Minimum (0)
        0x25, 0x01, //   Logical Maximum (1)
        0x75, 0x01, //   Report Size (1)
        0x95, 0x08, //   Report Count (8)
        0x81, 0x02, //   Input (Data, Variable, Absolute) — modifiers
        0x95, 0x01, //   Report Count (1)
        0x75, 0x08, //   Report Size (8)
        0x81, 0x01, //   Input (Constant) — reserved byte
        0x95, 0x06, //   Report Count (6)
        0x75, 0x08, //   Report Size (8)
        0x15, 0x00, //   Logical Minimum (0)
        0x25, 0x65, //   Logical Maximum (101)
        0x05, 0x07, //   Usage Page (Key codes)
        0x19, 0x00, //   Usage Minimum (0)
        0x29, 0x65, //   Usage Maximum (101)
        0x81, 0x00, //   Input (Data, Array) — key array (6 bytes)
        0x95, 0x05, //   Report Count (5)
        0x75, 0x01, //   Report Size (1)
        0x05, 0x08, //   Usage Page (LEDs)
        0x19, 0x01, //   Usage Minimum (1)
        0x29, 0x05, //   Usage Maximum (5)
        0x91, 0x02, //   Output (Data, Variable, Absolute) — LED report
        0x95, 0x01, //   Report Count (1)
        0x75, 0x03, //   Report Size (3)
        0x91, 0x01, //   Output (Constant) — LED padding
        0xC0        // End Collection (Application)
    };

    struct bt_hids_init_param init = {0};

    init.rep_map.data = report_map;
    init.rep_map.size = sizeof(report_map);
    init.info.bcd_hid = 0x0111; // USB HID 1.11
    init.info.b_country_code = 0x00;
    init.info.flags = BT_HIDS_REMOTE_WAKE | BT_HIDS_NORMALLY_CONNECTABLE;
    init.is_kb = true;
    init.pm_evt_handler = hids_pm_evt_handler;

    struct bt_hids_inp_rep *inp_rep = &init.inp_rep_group_init.reports[0];
    inp_rep->id = 0x00;
    inp_rep->size = DICTATION_INPUT_REPORT_LEN;
    inp_rep->handler = hids_inp_rep_handler;
    init.inp_rep_group_init.cnt++;

    int err = bt_hids_init(&hids_obj, &init);
    if (err) {
        LOG_ERR("bt_hids_init failed: %d", err);
        return err;
    }

    hid_registered = true;
    return 0;
}

static void hids_unregister(void)
{
    if (!hid_registered) {
        return;
    }
    int err = bt_hids_uninit(&hids_obj);
    if (err) {
        LOG_ERR("bt_hids_uninit failed: %d", err);
        return;
    }
}

// --- Dictation control-plane GATT service ---

static struct bt_uuid_128 dictation_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10040, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 dictation_control_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10041, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 dictation_text_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10042, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

static struct hid_dictation_status current_status(void)
{
    struct hid_dictation_status s = {0};
    s.version = HID_DICTATION_PROTOCOL_VERSION;
    s.hid_active = hid_registered;
    s.hid_pending = hid_wanted != hid_registered;
    s.active_session = dictation_ctx.active_session;
    s.last_finished_session = dictation_ctx.last_finished_session;
    s.last_error = dictation_ctx.last_error;
    s.error_detail = dictation_ctx.error_detail;
    s.chars_typed = dictation_ctx.pos;

    if (!hid_registered) {
        s.state = HID_DICTATION_STATE_DISABLED;
    } else if (dictation_ctx.typing_ready) {
        s.state = HID_DICTATION_STATE_TYPING;
    } else if (dictation_ctx.active_session != HID_DICTATION_SESSION_NONE) {
        s.state = HID_DICTATION_STATE_RECEIVING;
    } else if (dictation_ctx.last_error == HID_DICTATION_ERR_CANCELLED) {
        s.state = HID_DICTATION_STATE_IDLE; // cancellation is not a failure state
    } else if (dictation_ctx.last_error != HID_DICTATION_ERR_NONE) {
        s.state = HID_DICTATION_STATE_ERROR;
    } else if (dictation_ctx.last_finished_session != HID_DICTATION_SESSION_NONE) {
        s.state = HID_DICTATION_STATE_DONE;
    } else {
        s.state = HID_DICTATION_STATE_IDLE;
    }
    return s;
}

static void notify_status(void)
{
    struct hid_dictation_status s = current_status();
    // attrs[1] is the control characteristic value attribute.
    bt_gatt_notify(NULL, &dictation_service.attrs[1], &s, sizeof(s));
}

// --- Typing engine ---

static void typing_work_handler(struct k_work *work);
static void frame_timeout_handler(struct k_work *work);

K_WORK_DELAYABLE_DEFINE(typing_work, typing_work_handler);
K_WORK_DELAYABLE_DEFINE(frame_timeout_work, frame_timeout_handler);
static int send_report(const uint8_t report[DICTATION_INPUT_REPORT_LEN])
{
    if (conn_ref == NULL) {
        return -ENOTCONN;
    }
    int err = bt_hids_inp_rep_send(&hids_obj, conn_ref, 0, report, DICTATION_INPUT_REPORT_LEN, NULL);
    if (err == -EACCES) {
        // Nobody subscribed to HID input reports on this link.
        return -EACCES;
    }
    return err;
}

static void release_all_keys(void)
{
    uint8_t zero[DICTATION_INPUT_REPORT_LEN] = {0};
    (void) send_report(zero);
}

static void stop_typing(uint8_t error, uint8_t detail)
{
    k_work_cancel_delayable(&typing_work);
    k_work_cancel_delayable(&frame_timeout_work);
    if (dictation_ctx.typing_ready || dictation_ctx.active_session != HID_DICTATION_SESSION_NONE) {
        if (error == HID_DICTATION_ERR_NONE) {
            hid_dictation_core_abort(&dictation_ctx); // marks session finished
        } else {
            dictation_ctx.last_error = error;
            dictation_ctx.error_detail = detail;
            hid_dictation_core_abort(&dictation_ctx);
        }
        release_all_keys();
        notify_status();
    } else {
        dictation_ctx.last_error = error;
        dictation_ctx.error_detail = detail;
    }
}

static void typing_work_handler(struct k_work *work)
{
    ARG_UNUSED(work);

    if (!dictation_ctx.typing_ready || conn_ref == NULL) {
        return;
    }

    static uint32_t typing_started_ms;
    if (dictation_ctx.pos == 0 && !dictation_ctx.key_down) {
        typing_started_ms = k_uptime_get_32();
    }
    if (k_uptime_get_32() - typing_started_ms > DICTATION_TYPE_BUDGET_MS) {
        stop_typing(HID_DICTATION_ERR_TIMEOUT, dictation_ctx.active_session);
        return;
    }

    uint8_t report[DICTATION_INPUT_REPORT_LEN];
    enum hid_dictation_key_event evt = hid_dictation_core_next_key(&dictation_ctx, report);

    if (evt == HID_DICTATION_KEY_DONE) {
        return;
    }

    int err = send_report(report);
    if (err != 0) {
        uint8_t code = (err == -EACCES) ? HID_DICTATION_ERR_NOT_SUBSCRIBED : HID_DICTATION_ERR_INTERNAL;
        stop_typing(code, dictation_ctx.active_session);
        return;
    }

    k_work_reschedule(&typing_work, K_MSEC(DICTATION_KEY_INTERVAL_MS));
}

static void frame_timeout_handler(struct k_work *work)
{
    ARG_UNUSED(work);
    if (dictation_ctx.active_session != HID_DICTATION_SESSION_NONE && !dictation_ctx.typing_ready) {
        stop_typing(HID_DICTATION_ERR_TIMEOUT, dictation_ctx.active_session);
    }
}

// --- GATT handlers ---

static ssize_t
dictation_control_read(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    struct hid_dictation_status s = current_status();
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &s, sizeof(s));
}

static void dictation_control_ccc_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_INF("Client subscribed to dictation status");
    } else if (value == 0) {
        LOG_INF("Client unsubscribed from dictation status");
    }
}

static ssize_t dictation_control_write(struct bt_conn *conn,
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
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    const uint8_t cmd = ((const uint8_t *) buf)[0];
    if (cmd != HID_DICTATION_CMD_ENABLE && cmd != HID_DICTATION_CMD_DISABLE) {
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    bool enable = (cmd == HID_DICTATION_CMD_ENABLE);
    if (enable == hid_wanted) {
        notify_status();
        return len;
    }

    hid_wanted = enable;
    printk("hid_dictation: %s requested (reconnect to apply)\n", enable ? "enable" : "disable");
    if (!enable) {
        stop_typing(HID_DICTATION_ERR_NONE, 0);
    }
    notify_status();
    return len;
}

static ssize_t dictation_text_write(struct bt_conn *conn,
                                    const struct bt_gatt_attr *attr,
                                    const void *buf,
                                    uint16_t len,
                                    uint16_t offset,
                                    uint8_t flags)
{
    if (offset != 0) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    if (len < HID_DICTATION_FRAME_HDR_LEN || len > HID_DICTATION_FRAME_HDR_LEN + HID_DICTATION_FRAME_MAX_PAYLOAD) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    if (!hid_registered) {
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    enum hid_dictation_feed_result result = hid_dictation_core_feed(&dictation_ctx, (const uint8_t *) buf, len);

    switch (result) {
    case HID_DICTATION_FEED_ACCEPTED:
        k_work_reschedule(&frame_timeout_work, K_MSEC(DICTATION_FRAME_TIMEOUT_MS));
        break;
    case HID_DICTATION_FEED_COMPLETE:
        k_work_cancel_delayable(&frame_timeout_work);
        // Start typing from the system work queue; the first event presses,
        // the next releases — the engine never holds two keys at once.
        k_work_reschedule(&typing_work, K_NO_WAIT);
        break;
    case HID_DICTATION_FEED_CANCELLED:
        // The core already closed the session and recorded CANCELLED; only
        // make sure no key stays held. stop_typing would overwrite the error.
        release_all_keys();
        break;
    case HID_DICTATION_FEED_ERROR:
        release_all_keys();
        break;
    }

    notify_status();
    return len;
}

static struct bt_gatt_attr dictation_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&dictation_service_uuid),
    BT_GATT_CHARACTERISTIC(&dictation_control_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ | BT_GATT_PERM_WRITE,
                           dictation_control_read,
                           dictation_control_write,
                           NULL),
    BT_GATT_CCC(dictation_control_ccc_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&dictation_text_uuid.uuid,
                           BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_WRITE,
                           NULL,
                           dictation_text_write,
                           NULL),
};

static struct bt_gatt_service dictation_service = BT_GATT_SERVICE(dictation_service_attr);

// --- Runtime API ---

int hid_dictation_service_register(void)
{
    hid_dictation_core_init(&dictation_ctx, dictation_text, &dictation_limits);
    return bt_gatt_service_register(&dictation_service);
}

void hid_dictation_bt_ready(void)
{
#if defined(CONFIG_BT_SETTINGS)
    // Bonded HID hosts (the phone acting as HID host) reconnect faster and
    // encrypted. Settings subsystem was initialised by the app before
    // transport_start(); load it again now that the stack is up.
    int err = settings_load();
    if (err) {
        LOG_WRN("settings_load after bt_enable failed: %d", err);
    }
#endif
}

void hid_dictation_on_connected(struct bt_conn *conn)
{
    if (conn_ref != NULL) {
        bt_conn_unref(conn_ref);
    }
    conn_ref = bt_conn_ref(conn);

    if (hid_registered) {
        int err = bt_hids_connected(&hids_obj, conn);
        if (err) {
            LOG_ERR("bt_hids_connected failed: %d", err);
        }
    }
    notify_status();
}

void hid_dictation_on_disconnected(struct bt_conn *conn)
{
    // Forget everything about the session: no replay after reconnect.
    stop_typing(HID_DICTATION_ERR_NONE, 0);
    hid_dictation_core_init(&dictation_ctx, dictation_text, &dictation_limits);

    if (hid_registered) {
        int err = bt_hids_disconnected(&hids_obj, conn);
        if (err) {
            LOG_ERR("bt_hids_disconnected failed: %d", err);
        }
    }

    if (conn_ref != NULL) {
        bt_conn_unref(conn_ref);
        conn_ref = NULL;
    }

    // Apply the requested opt-in state while no link exists — the GATT table
    // must be final before advertising starts again.
    if (hid_wanted && !hid_registered) {
        hids_register();
        printk("hid_dictation: HID keyboard service registered\n");
    } else if (!hid_wanted && hid_registered) {
        hids_unregister();
        printk("hid_dictation: HID keyboard service removed\n");
    }
}

bool hid_dictation_hid_active(void)
{
    return hid_registered;
}

bool hid_dictation_wants_adv_restart(void)
{
    // Restart advertising only when the prototype flow is in play, so builds
    // and sessions that never touch the feature keep stock disconnect
    // behavior exactly.
    return hid_wanted || hid_registered;
}

void hid_dictation_button_pressed(void)
{
    if (dictation_ctx.typing_ready || dictation_ctx.active_session != HID_DICTATION_SESSION_NONE) {
        printk("hid_dictation: button press cancels active session\n");
        stop_typing(HID_DICTATION_ERR_CANCELLED, dictation_ctx.active_session);
    }
}
