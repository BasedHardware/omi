#include <assert.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#define K_FOREVER 0
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
static struct bt_gatt_service audio_service, storage_service;
static struct bt_conn connection, *current_connection;
static int connection_generation, pusher_wake_sem, ring_buf, write_sdcard_mutex;
static uint32_t file_num_array[2];
static uint16_t current_mtu;
static uint8_t heartbeat_count;
static bool tx_frame_pending, audio_subscribed, storage_notifications, sd_on;
/* The old callback sets this true on connection, before any subscriptions. */
static bool storage_is_on;
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
    (void) timeout;
    if (sem_calls++)
        longjmp(finish, 1);
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
static bool is_sd_on(void)
{
    return sd_on;
}
static bool write_to_storage(void)
{
    stored++;
    tx_frame_pending = false;
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

#include "production.inc"

static void check(bool connected, bool audio, bool storage, bool sd, int expected_sd, int expected_ble)
{
    current_connection = connected ? &connection : NULL;
    current_mtu = 251;
    storage_is_on = connected;
    audio_subscribed = audio;
    storage_notifications = storage;
    sd_on = sd;
    tx_frame_pending = true;
    stored = streamed = sem_calls = 0;
    if (setjmp(finish) == 0)
        pusher();
    assert(stored == expected_sd && streamed == expected_ble);
}

int main(void)
{
    check(false, false, false, true, 1, 0);
    check(true, false, false, true, 1, 0);
    check(true, true, false, true, 0, 1);
    check(true, false, true, true, 0, 0);
    check(true, true, true, true, 0, 1);
    check(true, false, false, false, 0, 0);
    puts("DevKit routing: disconnected, unsubscribed, live, storage sync and unavailable SD passed");
}
