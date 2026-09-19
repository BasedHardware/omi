// Test-only replacements for Zephyr/NCS boundaries. No radio or kernel is simulated.
#ifndef HID_RUNTIME_FAKES_H
#define HID_RUNTIME_FAKES_H
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#define CONFIG_LOG_DEFAULT_LEVEL 0
#define CONFIG_OMI_HID_DICTATION_MAX_TEXT_LEN 256
#define CONFIG_OMI_HID_DICTATION_KEY_INTERVAL_MS 12
#define CONFIG_OMI_HID_DICTATION_FRAME_TIMEOUT_MS 3000
#define CONFIG_OMI_HID_DICTATION_TYPE_BUDGET_MS 30000
#define BUILD_ASSERT(c, m) _Static_assert(c, m)
#define ARG_UNUSED(x) (void) (x)
#define LOG_MODULE_REGISTER(...)
#define LOG_INF(...)
#define LOG_ERR(...)
#define LOG_WRN(...)
#define printk(...) ((void) 0)
#define K_FOREVER 0
#define K_NO_WAIT 0
#define K_MSEC(x) (x)
struct k_mutex {
    unsigned depth;
};
#define K_MUTEX_DEFINE(n) static struct k_mutex n
static inline void k_mutex_lock(struct k_mutex *m, int timeout)
{
    (void) timeout;
    m->depth++;
}
static inline void k_mutex_unlock(struct k_mutex *m)
{
    assert(m->depth);
    m->depth--;
}
struct k_work {
    void (*handler)(struct k_work *);
};
struct k_work_delayable {
    struct k_work work;
    bool pending;
    uint32_t due;
};
#define K_WORK_DELAYABLE_DEFINE(n, h) static struct k_work_delayable n = {.work = {.handler = h}}
static uint32_t fake_now;
static inline uint32_t k_uptime_get_32(void)
{
    return fake_now;
}
static inline void k_sleep(int ms)
{
    fake_now += ms;
}
static inline int k_work_reschedule(struct k_work_delayable *w, int ms)
{
    w->pending = true;
    w->due = fake_now + ms;
    return 0;
}
static inline int k_work_cancel_delayable(struct k_work_delayable *w)
{
    w->pending = false;
    return 0;
}
struct bt_conn {
    int refs;
};
static unsigned fake_disconnects;
static inline struct bt_conn *bt_conn_ref(struct bt_conn *c)
{
    c->refs++;
    return c;
}
static inline void bt_conn_unref(struct bt_conn *c)
{
    assert(c->refs > 0);
    c->refs--;
}
#define BT_HCI_ERR_REMOTE_USER_TERM_CONN 0x13
static inline int bt_conn_disconnect(struct bt_conn *c, int reason)
{
    (void) c;
    (void) reason;
    fake_disconnects++;
    return 0;
}
struct bt_uuid {
    uint8_t type;
};
struct bt_uuid_128 {
    struct bt_uuid uuid;
};
#define BT_UUID_128_ENCODE(...) 0
#define BT_UUID_INIT_128(...) {0}
struct bt_gatt_attr {
    const void *uuid;
    const void *read;
    const void *write;
};
struct bt_gatt_service {
    struct bt_gatt_attr *attrs;
};
#define BT_GATT_PRIMARY_SERVICE(u) {.uuid = u}
#define BT_GATT_CHARACTERISTIC(u, prop, perm, r, w, data)                                                              \
    {.uuid = u},                                                                                                       \
    {                                                                                                                  \
        .read = r, .write = w                                                                                          \
    }
#define BT_GATT_CCC(h, perm) {.write = h}
#define BT_GATT_SERVICE(a) {.attrs = a}
#define BT_GATT_CCC_NOTIFY 1
#define BT_ATT_ERR_INVALID_OFFSET 7
#define BT_ATT_ERR_INVALID_ATTRIBUTE_LEN 13
#define BT_ATT_ERR_VALUE_NOT_ALLOWED 19
#define BT_GATT_ERR(e) (-(e))
static unsigned fake_notifications;
static inline int bt_gatt_notify(struct bt_conn *c, const struct bt_gatt_attr *a, const void *data, uint16_t len)
{
    (void) c;
    (void) a;
    (void) data;
    (void) len;
    fake_notifications++;
    return 0;
}
static inline ssize_t bt_gatt_attr_read(struct bt_conn *c,
                                        const struct bt_gatt_attr *a,
                                        void *buf,
                                        uint16_t len,
                                        uint16_t off,
                                        const void *data,
                                        uint16_t size)
{
    (void) c;
    (void) a;
    if (off > size)
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    if (len > size - off)
        len = size - off;
    memcpy(buf, (const uint8_t *) data + off, len);
    return len;
}
static inline int bt_gatt_service_register(struct bt_gatt_service *s)
{
    (void) s;
    return 0;
}
enum bt_hids_pm_evt { FAKE_PM_EVT };
enum bt_hids_notify_evt { BT_HIDS_CCCD_EVT_NOTIFY_ENABLED, BT_HIDS_CCCD_EVT_NOTIFY_DISABLED };
struct bt_hids_rep {
    int unused;
};
struct bt_hids_inp_rep {
    uint8_t id;
    uint16_t size;
    void (*handler)(enum bt_hids_notify_evt);
};
struct bt_hids_outp_feat_rep {
    uint8_t id;
    uint16_t size;
    void (*handler)(struct bt_hids_rep *, struct bt_conn *, bool);
};
struct bt_hids_init_param {
    struct {
        const uint8_t *data;
        size_t size;
    } rep_map;
    struct {
        uint16_t bcd_hid;
        uint8_t b_country_code;
        uint8_t flags;
    } info;
    bool is_kb;
    void (*pm_evt_handler)(enum bt_hids_pm_evt, struct bt_conn *);
    struct {
        struct bt_hids_inp_rep reports[1];
        unsigned cnt;
    } inp_rep_group_init;
    struct {
        struct bt_hids_outp_feat_rep reports[1];
        unsigned cnt;
    } outp_rep_group_init;
    void (*boot_kb_outp_rep_handler)(struct bt_hids_rep *, struct bt_conn *, bool);
};
#define BT_HIDS_REMOTE_WAKE 1
#define BT_HIDS_NORMALLY_CONNECTABLE 2
#define BT_HIDS_DEF(n, ...) static int n
static int fake_init_error, fake_uninit_error, fake_send_error;
static unsigned fake_failures_left, fake_send_attempts, fake_report_count;
static uint8_t fake_reports[2048][8];
static inline int bt_hids_init(int *h, struct bt_hids_init_param *p)
{
    (void) h;
    assert(p->inp_rep_group_init.reports[0].size == 8);
    return fake_init_error;
}
static inline int bt_hids_uninit(int *h)
{
    (void) h;
    return fake_uninit_error;
}
static inline int bt_hids_connected(int *h, struct bt_conn *c)
{
    (void) h;
    (void) c;
    return 0;
}
static inline int bt_hids_disconnected(int *h, struct bt_conn *c)
{
    (void) h;
    (void) c;
    return 0;
}
static inline int bt_hids_inp_rep_send(int *h, struct bt_conn *c, int index, const uint8_t *data, size_t len, void *cb)
{
    (void) h;
    (void) c;
    (void) index;
    (void) cb;
    assert(len == 8);
    fake_send_attempts++;
    if (fake_failures_left) {
        fake_failures_left--;
        return fake_send_error;
    }
    assert(fake_report_count < 2048);
    memcpy(fake_reports[fake_report_count++], data, 8);
    return 0;
}
#endif
