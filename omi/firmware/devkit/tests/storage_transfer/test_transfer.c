#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define SD_BLE_SIZE 440
#define FS_O_READ 1
#define FS_SEEK_SET 0
#define LOG_INF(...) ((void) 0)
#define LOG_PRINTK(...) ((void) 0)

struct fs_file_t {
    int unused;
};
struct bt_conn {
    int unused;
};
static struct {
    int attrs[2];
} storage_service;
static char read_buffer[] = "audio";
static uint8_t storage_write_buffer[440];
static uint8_t transport_started, current_read_num = 1, file_count = 1;
static uint32_t file_num_array[2], remaining_length, offset;
static int open_error, seek_error, read_result, close_error, notify_error;
static int opens, seeks, reads, closes, notifications, notified_size, seek_position;
static uint16_t mtu = 498;
static uint8_t notified[440];
static int move_read_pointer(uint8_t num)
{
    (void) num;
    return 0;
}
static uint32_t get_file_size(uint8_t num)
{
    (void) num;
    return file_num_array[0];
}
static void k_msleep(int ms)
{
    (void) ms;
}
static void fs_file_t_init(struct fs_file_t *file)
{
    (void) file;
}
static int fs_open(struct fs_file_t *file, const char *name, int flags)
{
    (void) file;
    (void) name;
    assert(flags == FS_O_READ);
    opens++;
    return open_error;
}
static int fs_seek(struct fs_file_t *file, int position, int whence)
{
    (void) file;
    (void) whence;
    seeks++;
    seek_position = position;
    return seek_error;
}
static int fs_read(struct fs_file_t *file, void *data, int amount)
{
    (void) file;
    reads++;
    if (read_result < 0)
        return read_result;
    int count = MIN(amount, read_result);
    for (int i = 0; i < count; i++)
        ((uint8_t *) data)[i] = (uint8_t) (seek_position + i);
    return count;
}
static int fs_close(struct fs_file_t *file)
{
    (void) file;
    closes++;
    return close_error;
}
static uint16_t bt_gatt_get_mtu(struct bt_conn *conn)
{
    (void) conn;
    return mtu;
}
static int bt_gatt_notify(struct bt_conn *conn, const void *attr, const void *data, uint16_t size)
{
    (void) conn;
    (void) attr;
    notifications++;
    notified_size = size;
    memcpy(notified, data, size);
    return notify_error;
}

/* Generated from the production files by run.py, not a second implementation. */
#include "production.inc"

static void reset(void)
{
    open_error = seek_error = close_error = notify_error = 0;
    opens = seeks = reads = closes = notifications = 0;
    read_result = 440;
    offset = 0;
    remaining_length = 880;
    mtu = 498;
}

int main(void)
{
    reset();
    notify_error = -ENOMEM;
    assert(write_to_gatt(NULL) == -ENOMEM);
    assert(offset == 0 && remaining_length == 880);
    uint8_t failed[440];
    memcpy(failed, notified, sizeof(failed));
    notify_error = 0;
    assert(write_to_gatt(NULL) == 0);
    assert(offset == 440 && remaining_length == 440 && seek_position == 0);
    assert(memcmp(failed, notified, 440) == 0);
    assert(write_to_gatt(NULL) == 0);
    assert(offset == 880 && remaining_length == 0 && seek_position == 440);

    reset();
    open_error = -EIO;
    assert(write_to_gatt(NULL) == -EIO);
    assert(seeks == 0 && reads == 0 && closes == 0 && notifications == 0 && offset == 0);
    reset();
    seek_error = -EINVAL;
    assert(write_to_gatt(NULL) == -EINVAL);
    assert(reads == 0 && closes == 1 && notifications == 0 && offset == 0);
    reset();
    read_result = -EIO;
    assert(write_to_gatt(NULL) == -EIO);
    assert(closes == 1 && notifications == 0 && offset == 0);
    reset();
    read_result = 123;
    assert(write_to_gatt(NULL) == -EIO);
    assert(notifications == 0 && offset == 0 && remaining_length == 880);
    reset();
    read_result = 0;
    assert(write_to_gatt(NULL) == -EIO && notifications == 0);
    reset();
    close_error = -EIO;
    assert(write_to_gatt(NULL) == -EIO && notifications == 0 && offset == 0);

    reset();
    remaining_length = 100;
    assert(write_to_gatt(NULL) == 0);
    assert(offset == 100 && remaining_length == 0 && notified_size == 100);
    assert(write_to_gatt(NULL) == 0 && notifications == 1);
    reset();
    mtu = 442;
    assert(write_to_gatt(NULL) == -EMSGSIZE && reads == 0 && offset == 0);
    mtu = 443;
    assert(write_to_gatt(NULL) == 0 && notified_size == 440);

    reset();
    file_num_array[0] = 440;
    offset = 880;
    assert(setup_storage_tx() == -EINVAL && remaining_length == 0);
    offset = 440;
    assert(setup_storage_tx() == 0 && remaining_length == 0);
    offset = 0;
    assert(setup_storage_tx() == 0 && remaining_length == 440);
    puts("DevKit storage transfer: retry identity, filesystem failures, MTU, tail and resume bounds passed");
}
