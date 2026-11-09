/* Execute the production advertising worker with BLE RX scheduled during HCI. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define MAX_DEVICE_NAME_LEN 26
#define CONFIG_BT_DEVICE_NAME "Omi"
#define CONFIG_BT_DEVICE_NAME_DYNAMIC 1
#define ARG_UNUSED(x) (void) (x)
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
static unsigned warnings;
#define LOG_WRN(...) (++warnings)
#define LOG_INF(...) ((void) 0)
#define BT_DATA_UUID16_ALL 3
#define BT_DATA_NAME_COMPLETE 9
#define BT_UUID_DIS_VAL 0x180A
#define BT_UUID_16_ENCODE(x) 0x0A, 0x18
#define BT_DATA_BYTES(type, ...)                                                                                       \
    {                                                                                                                  \
        type, sizeof((uint8_t[]){__VA_ARGS__}), (uint8_t[])                                                            \
        {                                                                                                              \
            __VA_ARGS__                                                                                                \
        }                                                                                                              \
    }
// clang-format off: local and CI versions disagree on a brace in a macro body.
#define BT_DATA(type, pointer, length) {type, length, (const uint8_t *) (pointer)}
// clang-format on
#define BT_LE_ADV_CONN NULL
struct bt_data {
    uint8_t type;
    size_t data_len;
    const uint8_t *data;
};
static const struct bt_data bt_ad[] = {{0, 0, NULL}};
struct k_work {
    int unused;
};
struct k_work_delayable {
    struct k_work work;
};
#define K_NO_WAIT 0
#define K_MSEC(ms) (ms)
struct k_spinlock {
    bool held;
};
typedef int k_spinlock_key_t;
static int lock_depth;
static k_spinlock_key_t k_spin_lock(struct k_spinlock *lock)
{
    assert(!lock->held);
    lock->held = true;
    ++lock_depth;
    return 0;
}
static void k_spin_unlock(struct k_spinlock *lock, k_spinlock_key_t key)
{
    (void) key;
    assert(lock->held);
    lock->held = false;
    --lock_depth;
}
static unsigned submissions;
static bool scheduled;
static int scheduled_delay;
static int k_work_submit(struct k_work *work)
{
    (void) work;
    scheduled = true;
    scheduled_delay = 0;
    ++submissions;
    return 1;
}
static int k_work_reschedule(struct k_work_delayable *work, int delay)
{
    (void) work;
    scheduled = true;
    scheduled_delay = delay;
    ++submissions;
    return 1;
}
static int bt_set_name(const char *name);
static int bt_le_adv_update_data(const struct bt_data *, size_t, const struct bt_data *, size_t);
static int bt_le_adv_start(const void *, const struct bt_data *, size_t, const struct bt_data *, size_t);
#include "advertising.inc"
static const char *expected;
static const char *interleave;
static bool in_set_name;
static bool advertising_enabled = true;
static bool bluetooth_rx;
static char applied_name[MAX_DEVICE_NAME_LEN];

static int bt_set_name(const char *name)
{
    assert(lock_depth == 0); /* HCI must not run with a spinlock held. */
    assert(!bluetooth_rx);
    assert(strcmp(name, expected) == 0);
    if (interleave && in_set_name) {
        update_advertising_name(interleave);
        assert(strcmp(name, expected) == 0);
    }
    return 0;
}

static int bt_le_adv_update_data(const struct bt_data *ad, size_t ad_len, const struct bt_data *sd, size_t sd_len)
{
    (void) ad;
    (void) ad_len;
    assert(lock_depth == 0 && sd_len == 2);
    assert(!bluetooth_rx);
    assert(sd[1].data_len == strlen(expected));
    assert(memcmp(sd[1].data, expected, sd[1].data_len + 1) == 0);
    if (interleave && !in_set_name) {
        update_advertising_name(interleave);
        assert(sd[1].data_len == strlen(expected));
        assert(memcmp(sd[1].data, expected, sd[1].data_len + 1) == 0);
    }
    if (!advertising_enabled) {
        return -EAGAIN;
    }
    memcpy(applied_name, sd[1].data, sd[1].data_len + 1);
    return 0;
}

static int
bt_le_adv_start(const void *params, const struct bt_data *ad, size_t ad_len, const struct bt_data *sd, size_t sd_len)
{
    (void) params;
    return bt_le_adv_update_data(ad, ad_len, sd, sd_len);
}

static void run_work(void)
{
    assert(scheduled);
    scheduled = false;
    adv_name_update_work_handler(NULL);
}

static unsigned drain_work(void)
{
    unsigned attempts = 0;
    while (scheduled) {
        assert(++attempts <= 6); /* One attempt plus at most five retries. */
        run_work();
        if (scheduled)
            assert(scheduled_delay > 0); /* Never spin on EAGAIN. */
    }
    return attempts;
}

static void disconnect_before_resume(void)
{
    /* Zephyr resumes advertising only after returning from this callback. */
    assert(!advertising_enabled);
    bluetooth_rx = true;
#include "disconnected.inc"
    bluetooth_rx = false;
}

int main(void)
{
    for (unsigned phase = 0; phase < 2; ++phase) {
        in_set_name = phase == 0;
        update_advertising_name("first");
        expected = "first";
        interleave = "second-longer";
        run_work();
        interleave = NULL;
        expected = "second-longer";
        run_work();
    }
    expected = "Omi";
    update_advertising_name("");
    run_work();
    expected = "abcdefghijklmnopqrstuvwxy";
    update_advertising_name(expected);
    run_work();
    assert(submissions == 6);
    puts("device name advertising snapshots survive BLE RX during both HCI calls");

    advertising_enabled = false; /* A phone occupies the single connection. */
    expected = "after-disconnect";
    update_advertising_name(expected);
    assert(drain_work() <= 6); /* Phone may stay connected past the retry budget. */
    assert(strcmp(applied_name, expected) != 0);
    disconnect_before_resume();
    /* Even delayed work can race host resume: fail once more before enabling. */
    if (scheduled)
        run_work();
    advertising_enabled = true;
    drain_work();
    assert(strcmp(applied_name, expected) == 0);
    puts("pending name applied after disconnect/resume despite EAGAIN");

    advertising_enabled = false;
    expected = "persistent-failure";
    update_advertising_name(expected);
    unsigned before_warnings = warnings;
    drain_work();
    assert(warnings > before_warnings && !scheduled);
    before_warnings = warnings;
    disconnect_before_resume();
    drain_work();
    assert(warnings > before_warnings && !scheduled);
    puts("persistent advertising failure exhausts a bounded delayed retry budget and warns");
    advertising_enabled = true;
    assert(apply_advertising_name(true) == 0); /* The boot path uses the saved name. */
    assert(strcmp(applied_name, expected) == 0);
}
