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

// The whole typing budget must cover max text at the configured two-reports-
// per-character pacing, or a long session could be killed mid-word by design.
BUILD_ASSERT(CONFIG_OMI_HID_DICTATION_MAX_TEXT_LEN * 2 * CONFIG_OMI_HID_DICTATION_KEY_INTERVAL_MS <=
                 CONFIG_OMI_HID_DICTATION_TYPE_BUDGET_MS,
             "typing budget must cover max text at configured pacing");

static uint8_t dictation_text[CONFIG_OMI_HID_DICTATION_MAX_TEXT_LEN];
static struct hid_dictation_limits dictation_limits = {
    .max_text_len = sizeof(dictation_text),
};
static struct hid_dictation_ctx dictation_ctx;

// Opt-in state. RAM-only by design: a power cycle returns the pendant to
// runtime HID-off behavior if the firmware boots; this is not firmware rollback.
static bool hid_wanted;     // requested by the app
static bool hid_registered; // HIDS currently in the GATT table

static struct bt_conn *conn_ref; // last connection handed to on_connected

// Serializes dictation state (dictation_ctx, conn_ref, enable flags) across
// the BT RX thread (GATT writes, connect/disconnect callbacks) and the
// system workqueue (typing/timeout work). Zephyr k_mutex is recursive, so
// locked helpers may call each other; nothing calls back into this module
// while the lock is held.
K_MUTEX_DEFINE(dictation_lock);

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

// Keyboard LED output report (caps lock etc.): accepted and ignored. The
// pendant is a typer, not a feedback surface; LEDs state is not surfaced.
static void hids_kb_outp_rep_handler(struct bt_hids_rep *rep, struct bt_conn *conn, bool write)
{
    ARG_UNUSED(rep);
    ARG_UNUSED(conn);
    ARG_UNUSED(write);
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

    // The report map declares the standard LED output report; register it so
    // report-protocol hosts find the matching Report characteristic, and wire
    // boot-protocol LED writes to the same ignoring handler.
    struct bt_hids_outp_feat_rep *outp_rep = &init.outp_rep_group_init.reports[0];
    outp_rep->id = 0x00;
    outp_rep->size = 1;
    outp_rep->handler = hids_kb_outp_rep_handler;
    init.outp_rep_group_init.cnt++;
    init.boot_kb_outp_rep_handler = hids_kb_outp_rep_handler;

    int err = bt_hids_init(&hids_obj, &init);
    if (err) {
        LOG_ERR("bt_hids_init failed: %d", err);
        return err;
    }

    hid_registered = true;
    return 0;
}

// bt_hids_uninit() only fails when bt_gatt_service_unregister() fails, in
// which case the service is still in the GATT table — so hid_registered must
// stay true and the next enable cycle skips re-registration on purpose.
// Every other path (including the internal pool/ctx cleanup) leaves the
// service removed and clears the flag.
static int hids_unregister(void)
{
    if (!hid_registered) {
        return 0;
    }
    int err = bt_hids_uninit(&hids_obj);
    if (err) {
        LOG_ERR("bt_hids_uninit failed: %d (service still registered)", err);
        return err;
    }
    hid_registered = false;
    return 0;
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
    // Attribute layout: [0] primary service, [1] characteristic declaration,
    // [2] characteristic VALUE. Notify on the value attribute.
    bt_gatt_notify(NULL, &dictation_service.attrs[2], &s, sizeof(s));
}

// --- Typing engine ---

static void typing_work_handler(struct k_work *work);
static void frame_timeout_handler(struct k_work *work);

K_WORK_DELAYABLE_DEFINE(typing_work, typing_work_handler);
K_WORK_DELAYABLE_DEFINE(frame_timeout_work, frame_timeout_handler);
// Track reports accepted by the BLE stack independently of the core cursor.
// next_key advances before transmission; a failed RELEASE must still remember
// the preceding successful PRESS. All accesses hold dictation_lock.
static bool report_key_held;

static int send_report(const uint8_t report[DICTATION_INPUT_REPORT_LEN])
{
    if (conn_ref == NULL) {
        return -ENOTCONN;
    }
    int err = bt_hids_inp_rep_send(&hids_obj, conn_ref, 0, report, DICTATION_INPUT_REPORT_LEN, NULL);
    if (err == 0) {
        report_key_held = report[0] != 0 || report[2] != 0;
    }
    if (err == -EACCES) {
        // Nobody subscribed to HID input reports on this link.
        return -EACCES;
    }
    return err;
}

static int send_zero_report(void)
{
    uint8_t zero[DICTATION_INPUT_REPORT_LEN] = {0};
    return send_report(zero);
}

static void release_retry_delay(void)
{
    k_sleep(K_MSEC(10));
}

// Bounded retry of the release report; if a key may still be held and no
// attempt could be queued, fail closed by dropping the link — the HID host
// releases every key of a disconnected keyboard by specification.
// key_held must be captured BEFORE any core state mutation that could clear
// it (abort/cancel), or a physically-held key would look released.
static void release_all_keys(bool key_held)
{
    if (hid_dictation_core_release_all(send_zero_report, release_retry_delay, key_held || report_key_held, 3) != 0) {
        LOG_ERR("key release could not be queued; failing closed (drop link)");
        struct bt_conn *conn = conn_ref;
        if (conn != NULL) {
            int err = bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
            if (err) {
                LOG_ERR("fail-closed disconnect failed: %d", err);
            }
        }
    }
}

// Callers hold dictation_lock. Cancels pending work, closes the session,
// releases every held key, and publishes the terminal status. Because this
// runs under the same lock as the typing handler, a handler in flight either
// finishes before us (its press is released by our release_all_keys below)
// or observes the cleared session state and exits — no press can survive
// cancellation's final release.
static void stop_typing_locked(uint8_t error, uint8_t detail)
{
    k_work_cancel_delayable(&typing_work);
    k_work_cancel_delayable(&frame_timeout_work);
    if (dictation_ctx.typing_ready || dictation_ctx.active_session != HID_DICTATION_SESSION_NONE) {
        if (error != HID_DICTATION_ERR_NONE) {
            dictation_ctx.last_error = error;
            dictation_ctx.error_detail = detail;
        }
        bool key_held = dictation_ctx.key_down;   // before abort clears it
        hid_dictation_core_abort(&dictation_ctx); // marks session finished
        release_all_keys(key_held);
    } else {
        dictation_ctx.last_error = error;
        dictation_ctx.error_detail = detail;
    }
}

static void typing_work_handler(struct k_work *work)
{
    ARG_UNUSED(work);

    k_mutex_lock(&dictation_lock, K_FOREVER);

    if (!dictation_ctx.typing_ready || conn_ref == NULL) {
        k_mutex_unlock(&dictation_lock);
        return;
    }

    static uint32_t typing_started_ms;
    if (dictation_ctx.pos == 0 && !dictation_ctx.key_down) {
        typing_started_ms = k_uptime_get_32();
    }
    if (k_uptime_get_32() - typing_started_ms > DICTATION_TYPE_BUDGET_MS) {
        stop_typing_locked(HID_DICTATION_ERR_TIMEOUT, dictation_ctx.active_session);
        k_mutex_unlock(&dictation_lock);
        return;
    }

    uint8_t report[DICTATION_INPUT_REPORT_LEN];
    enum hid_dictation_key_event evt = hid_dictation_core_next_key(&dictation_ctx, report);

    if (evt == HID_DICTATION_KEY_DONE) {
        // Session finished: last emitted report was the final release; publish
        // DONE so notification-based completion waits resolve immediately.
        notify_status();
        k_mutex_unlock(&dictation_lock);
        return;
    }

    int err = send_report(report);
    if (err != 0) {
        uint8_t code = (err == -EACCES) ? HID_DICTATION_ERR_NOT_SUBSCRIBED : HID_DICTATION_ERR_INTERNAL;
        stop_typing_locked(code, dictation_ctx.active_session);
        k_mutex_unlock(&dictation_lock);
        return;
    }

    k_work_reschedule(&typing_work, K_MSEC(DICTATION_KEY_INTERVAL_MS));
    k_mutex_unlock(&dictation_lock);
}

static void frame_timeout_handler(struct k_work *work)
{
    ARG_UNUSED(work);
    k_mutex_lock(&dictation_lock, K_FOREVER);
    if (dictation_ctx.active_session != HID_DICTATION_SESSION_NONE && !dictation_ctx.typing_ready) {
        stop_typing_locked(HID_DICTATION_ERR_TIMEOUT, dictation_ctx.active_session);
    }
    k_mutex_unlock(&dictation_lock);
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

    k_mutex_lock(&dictation_lock, K_FOREVER);

    bool enable = (cmd == HID_DICTATION_CMD_ENABLE);
    if (enable == hid_wanted) {
        notify_status();
        k_mutex_unlock(&dictation_lock);
        return len;
    }

    hid_wanted = enable;
    printk("hid_dictation: %s requested (reconnect to apply)\n", enable ? "enable" : "disable");
    if (!enable) {
        stop_typing_locked(HID_DICTATION_ERR_NONE, 0);
    }
    notify_status();
    k_mutex_unlock(&dictation_lock);
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

    if (!hid_registered || !hid_wanted) {
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    k_mutex_lock(&dictation_lock, K_FOREVER);

    // Capture before feed: a CANCEL/ERROR for the active session clears
    // key_down in the core while a physical press may still be outstanding.
    bool key_held = dictation_ctx.key_down;
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
        release_all_keys(key_held);
        break;
    case HID_DICTATION_FEED_ERROR:
        release_all_keys(key_held);
        break;
    case HID_DICTATION_FEED_REJECTED:
        // Reject the write without changing the live session or its status.
        k_mutex_unlock(&dictation_lock);
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    notify_status();
    k_mutex_unlock(&dictation_lock);
    return len;
}

static struct bt_gatt_attr dictation_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&dictation_service_uuid),
    // Encrypted/bonded link required: committed text is user content typed
    // into whatever field has focus; it must never ride a plaintext link.
    // iOS pairs transparently on the first encrypted access (the ENABLE
    // write), which is also when the HID half needs the bond.
    BT_GATT_CHARACTERISTIC(&dictation_control_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ_ENCRYPT | BT_GATT_PERM_WRITE_ENCRYPT,
                           dictation_control_read,
                           dictation_control_write,
                           NULL),
    BT_GATT_CCC(dictation_control_ccc_handler, BT_GATT_PERM_READ_ENCRYPT | BT_GATT_PERM_WRITE_ENCRYPT),
    BT_GATT_CHARACTERISTIC(&dictation_text_uuid.uuid,
                           BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_WRITE_ENCRYPT,
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
    k_mutex_lock(&dictation_lock, K_FOREVER);
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
    k_mutex_unlock(&dictation_lock);
}

void hid_dictation_on_disconnected(struct bt_conn *conn)
{
    // Forget everything about the session: no replay after reconnect.
    k_mutex_lock(&dictation_lock, K_FOREVER);
    stop_typing_locked(HID_DICTATION_ERR_NONE, 0);
    hid_dictation_core_init(&dictation_ctx, dictation_text, &dictation_limits);
    report_key_held = false; // the disconnected HID host no longer owns held keys

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
        if (hids_unregister() == 0) {
            printk("hid_dictation: HID keyboard service removed\n");
        }
    }
    k_mutex_unlock(&dictation_lock);
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
    // Button work races GATT writes on the Bluetooth RX thread. Inspect and
    // cancel under one lock so session identity cannot change between them.
    k_mutex_lock(&dictation_lock, K_FOREVER);
    if (dictation_ctx.typing_ready || dictation_ctx.active_session != HID_DICTATION_SESSION_NONE) {
        printk("hid_dictation: button press cancels active session\n");
        stop_typing_locked(HID_DICTATION_ERR_CANCELLED, dictation_ctx.active_session);
    }
    k_mutex_unlock(&dictation_lock);
}
