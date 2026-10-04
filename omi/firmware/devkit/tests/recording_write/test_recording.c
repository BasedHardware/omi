#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>

#define FS_O_WRITE 1
#define FS_SEEK_END 2
#define FS_SEEK_SET 0
#define OPUS_PREFIX_LENGTH 1
#define MAX_WRITE_SIZE 440
#define LOG_ERR(...) ((void) 0)
struct fs_file_t {
    int unused;
};
static struct fs_file_t recording_file;
static bool recording_file_open;
static int recording_file_mutex, mutex_depth, mutations;
#define K_FOREVER 0
static void k_mutex_lock(int *mutex, int timeout)
{
    (void) mutex;
    (void) timeout;
    assert(mutex_depth++ == 0);
}
static void k_mutex_unlock(int *mutex)
{
    (void) mutex;
    assert(--mutex_depth == 0);
}
static int clear_audio_file_locked(uint8_t num)
{
    (void) num;
    assert(!recording_file_open && mutex_depth == 1);
    mutations++;
    return 0;
}
static int move_write_pointer_locked(uint8_t num)
{
    return clear_audio_file_locked(num);
}
static int delete_audio_file_locked(uint8_t num)
{
    return clear_audio_file_locked(num);
}
static void sd_off_locked(void)
{
    assert(!recording_file_open && mutex_depth == 1);
    mutations++;
}
static int opens, end_seeks, syncs;
static char write_buffer[] = "audio";
static off_t pending_write_offset = -1;
static uint8_t disk[4096], storage_temp_data[MAX_WRITE_SIZE], tx_buffer[322];
static uint16_t buffer_offset, tx_buffer_size;
static int disk_size, position, open_error, seek_error, sync_error, close_error;
static int max_write, fail_write_call, write_calls, consumed, closes;
static bool frame_available, freed, storage_retry_pending;
static void fs_file_t_init(struct fs_file_t *file)
{
    (void) file;
}
static int fs_open(struct fs_file_t *file, const char *path, int flags)
{
    (void) file;
    (void) path;
    assert(flags == FS_O_WRITE);
    opens++;
    position = 0;
    return open_error;
}
static int fs_seek(struct fs_file_t *file, off_t value, int whence)
{
    (void) file;
    if (whence == FS_SEEK_END)
        end_seeks++;
    if (seek_error)
        return seek_error;
    position = (whence == FS_SEEK_END ? disk_size : 0) + value;
    return 0;
}
static off_t fs_tell(struct fs_file_t *file)
{
    (void) file;
    return position;
}
static int fs_write(struct fs_file_t *file, const void *data, uint32_t length)
{
    (void) file;
    write_calls++;
    if (write_calls == fail_write_call)
        return -EIO;
    int count = length < (uint32_t) max_write ? (int) length : max_write;
    assert(position + count <= (int) sizeof(disk));
    memcpy(disk + position, data, count);
    position += count;
    if (position > disk_size)
        disk_size = position;
    return count;
}
static int fs_sync(struct fs_file_t *file)
{
    (void) file;
    syncs++;
    return sync_error;
}
static int fs_close(struct fs_file_t *file)
{
    (void) file;
    closes++;
    return close_error;
}
static bool load_tx_frame(void)
{
    return frame_available;
}
static void consume_tx_frame(void)
{
    consumed++;
    frame_available = false;
}
static char *generate_new_audio_header(uint8_t num)
{
    (void) num;
    freed = false;
    return write_buffer;
}
static void k_free(char *p)
{
    (void) p;
    freed = true;
}
static int create_file(const char *path)
{
    assert(!freed && path == write_buffer);
    return -EIO;
}

#include "production.inc"

static void reset(uint16_t packed)
{
    memset(disk, 0x55, sizeof(disk));
    memset(storage_temp_data, 0x33, sizeof(storage_temp_data));
    memset(tx_buffer, 0x77, sizeof(tx_buffer));
    disk_size = 880;
    position = 0;
    pending_write_offset = -1;
    recording_file_open = false;
    opens = end_seeks = syncs = mutations = 0;
    assert(mutex_depth == 0);
    buffer_offset = packed;
    tx_buffer_size = 40;
    frame_available = true;
    storage_retry_pending = false;
    open_error = seek_error = sync_error = close_error = 0;
    write_calls = fail_write_call = consumed = closes = 0;
    max_write = 440;
}

int main(void)
{
    reset(420);
    max_write = 100;
    fail_write_call = 2;
    assert(!write_to_storage());
    assert(disk_size == 980 && pending_write_offset == 880);
    assert(consumed == 0 && buffer_offset == 420 && closes == 1 && storage_retry_pending);
    fail_write_call = 0;
    assert(write_to_storage());
    assert(disk_size == 1320 && pending_write_offset == -1 && !storage_retry_pending);
    assert(consumed == 1 && buffer_offset == 41 && storage_temp_data[0] == 40);
    for (int i = 0; i < 880; i++)
        assert(disk[i] == 0x55);
    for (int i = 880; i < 1300; i++)
        assert(disk[i] == 0x33);
    assert(disk[1300] == 40);

    reset(398); /* 398 + length byte + 40 payload bytes = 439 */
    sync_error = -EIO;
    assert(!write_to_storage());
    assert(consumed == 0 && buffer_offset == 398 && disk_size == 1320);
    sync_error = 0;
    assert(write_to_storage());
    assert(consumed == 1 && buffer_offset == 0 && disk_size == 1320);
    assert(disk[1278] == 40 && disk[1279] == 0x77);

    reset(420);
    close_error = -EIO;
    assert(write_to_storage() && consumed == 1 && disk_size == 1320);
    assert(clear_audio_file(1) == -EIO && mutations == 0 && !recording_file_open);
    close_error = 0;
    reset(420);
    open_error = -EIO;
    assert(!write_to_storage() && consumed == 0 && write_calls == 0 && closes == 0);
    reset(420);
    seek_error = -EINVAL;
    assert(!write_to_storage() && consumed == 0 && write_calls == 0 && closes == 1);
    reset(420);
    max_write = 0;
    assert(!write_to_storage() && consumed == 0 && pending_write_offset == 880);
    max_write = 440;
    assert(write_to_storage() && disk_size == 1320);
    reset(0);
    assert(write_to_storage() && consumed == 1 && write_calls == 0 && buffer_offset == 41);
    reset(0);
    tx_buffer_size = 256;
    assert(!write_to_storage() && consumed == 0 && buffer_offset == 0);
    assert(initialize_audio_file(1) == -EIO && freed);
    reset(0);
    uint8_t payload[440];
    memset(payload, 0x22, sizeof(payload));
    assert(write_to_file(payload, sizeof(payload)) == 440);
    assert(write_to_file(payload, sizeof(payload)) == 440);
    assert(opens == 1 && end_seeks == 1 && syncs == 2 && closes == 0);
    assert(disk_size == 1760 && recording_file_open);
    fail_write_call = write_calls + 2;
    max_write = 100;
    assert(write_to_file(payload, sizeof(payload)) == -EIO);
    assert(pending_write_offset == 1760 && !recording_file_open && disk_size == 1860);
    fail_write_call = 0;
    assert(write_to_file(payload, sizeof(payload)) == 440 && disk_size == 2200);
    assert(opens == 2 && end_seeks == 1);
    assert(move_write_pointer(1) == 0 && mutations == 1 && !recording_file_open);
    assert(write_to_file(payload, sizeof(payload)) == 440);
    assert(delete_audio_file(1) == 0 && mutations == 2 && !recording_file_open);
    assert(write_to_file(payload, sizeof(payload)) == 440);
    sd_off();
    assert(mutations == 3 && !recording_file_open);
    puts("DevKit recording: partial-write retry, sync/close errors, frame retention and file creation passed");
}
