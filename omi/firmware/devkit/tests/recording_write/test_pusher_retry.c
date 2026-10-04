#include <assert.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#define K_FOREVER 0
#define K_MSEC(ms) (ms)
#define MINIMAL_PACKET_SIZE 100
#define MAX_STORAGE_BYTES 0xFFFF0000
#define BT_GATT_CCC_NOTIFY 1
#define LOG_PRINTK(...) ((void) 0)
typedef int atomic_val_t;
struct bt_conn {
    int unused;
};
struct bt_gatt_service {
    int attrs[2];
};
static struct bt_gatt_service audio_service;
struct bt_gatt_service storage_service;
static struct bt_conn *current_connection;
static int connection_generation, pusher_wake_sem, ring_buf, write_sdcard_mutex;
static uint32_t file_num_array[2];
static uint16_t current_mtu;
static uint8_t heartbeat_count;
static bool tx_frame_pending, audio_subscribed, storage_notifications, sd_on;
/* The old callback sets this true on connection, before any subscriptions. */
static bool storage_is_on;
static bool storage_retry_pending;
static bool use_storage = true;
bool offline_storage_is_available(void)
{
    return use_storage && sd_on;
}
static int stored, streamed;
static jmp_buf finish;
static int sem_calls;
static void k_msleep(int ms)
{
    (void) ms;
}
static void k_sem_take(int *sem, int timeout)
{
    (void) sem;
    if (sem_calls++ == 2)
        longjmp(finish, 1);
    if (sem_calls == 2)
        assert(timeout != K_FOREVER);
}
static atomic_val_t atomic_get(int *value)
{
    return *value;
}
static void update_file_size(void) {}
static bool ring_buf_is_empty(int *buf)
{
    (void) buf;
    return true;
}
static struct bt_conn *bt_conn_ref(struct bt_conn *conn)
{
    return conn;
}
static void bt_conn_unref(struct bt_conn *conn)
{
    (void) conn;
}
static bool bt_gatt_is_subscribed(struct bt_conn *conn, const void *attr, int mode)
{
    (void) conn;
    (void) mode;
    return attr == &audio_service.attrs[1] ? audio_subscribed : storage_notifications;
}
static void k_mutex_lock(int *mutex, int timeout)
{
    (void) mutex;
    (void) timeout;
}
static void k_mutex_unlock(int *mutex)
{
    (void) mutex;
}
bool is_sd_on(void)
{
    return sd_on;
}
static bool write_to_storage(void)
{
    stored++;
    if (stored == 1) {
        storage_retry_pending = true;
        return false;
    }
    tx_frame_pending = false;
    storage_retry_pending = false;
    return true;
}
static bool push_to_gatt(struct bt_conn *conn)
{
    (void) conn;
    streamed++;
    tx_frame_pending = false;
    return true;
}
static void k_yield(void) {}

#include "pusher.inc"

int main(void)
{
    current_connection = NULL;
    current_mtu = 251;
    storage_is_on = false;
    audio_subscribed = false;
    storage_notifications = false;
    sd_on = true;
    tx_frame_pending = true;
    stored = streamed = sem_calls = 0;
    if (setjmp(finish) == 0)
        pusher();
    assert(stored == 2 && streamed == 0 && !tx_frame_pending);
    puts("DevKit pusher: pending SD failure retries without a producer wakeup");
}
