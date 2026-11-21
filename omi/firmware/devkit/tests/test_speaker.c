#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define MAX_BLOCK_SIZE 10000
#define PACKET_SIZE 400
#define I2S_DIR_TX 0
#define I2S_TRIGGER_START 1
#define I2S_TRIGGER_DRAIN 2
#define I2S_TRIGGER_DROP 3
#define K_MSEC(x) (x)
struct bt_conn {
    int refs;
};
static uint8_t memory[MAX_BLOCK_SIZE];
static void *rx_buffer = memory;
static uint16_t current_length, offset, playback_bytes;
static int playing, playback_ready, mem_slab, audio_speaker;
static struct bt_conn *playback_conn;
static bool dma_owns, notified, success;
static int write_error, trigger_error, allocation_error;
static size_t written;
static int triggers[3], trigger_count;
static uint32_t sys_get_le32(const void *p)
{
    const uint8_t *b = p;
    return b[0] | (uint32_t) b[1] << 8 | (uint32_t) b[2] << 16 | (uint32_t) b[3] << 24;
}
static uint16_t sys_get_le16(const void *p)
{
    const uint8_t *b = p;
    return b[0] | (uint16_t) b[1] << 8;
}
static int atomic_get(int *p)
{
    return *p;
}
static void atomic_set(int *p, int v)
{
    *p = v;
}
static void atomic_clear(int *p)
{
    *p = 0;
}
static struct bt_conn *bt_conn_ref(struct bt_conn *p)
{
    p->refs++;
    return p;
}
static void bt_conn_unref(struct bt_conn *p)
{
    p->refs--;
}
static void k_sem_give(int *p)
{
    (*p)++;
}
static int i2s_write(int device, void *data, size_t bytes)
{
    (void) device;
    assert(data == memory && !dma_owns);
    if (write_error)
        return write_error;
    written = bytes;
    dma_owns = true;
    return 0;
}
static int i2s_trigger(int device, int direction, int command)
{
    (void) device;
    (void) direction;
    assert(dma_owns);
    triggers[trigger_count++] = command;
    return command == I2S_TRIGGER_START ? trigger_error : 0;
}
static int k_mem_slab_alloc(int *slab, void **buffer, int deadline)
{
    (void) slab;
    assert(dma_owns && !notified && rx_buffer == NULL);
    assert(deadline == 1000);
    if (allocation_error)
        return allocation_error;
    dma_owns = false;
    *buffer = memory;
    return 0;
}
static void speaker_notify_complete(struct bt_conn *conn, bool ok)
{
    assert(conn->refs == 1 && !playing);
    assert(!ok || !dma_owns);
    notified = true;
    success = ok;
}
/* PRODUCTION */
static void reset(void)
{
    current_length = offset = playback_bytes = 0;
    playing = playback_ready = write_error = trigger_error = allocation_error = 0;
    notified = success = dma_owns = false;
    written = trigger_count = 0;
    rx_buffer = memory;
    memset(memory, 0, sizeof(memory));
}
int main(void)
{
    struct bt_conn conn = {0};
    uint8_t header[] = {0x90, 1, 0, 0}; // 400 mono bytes, exact packet multiple
    uint8_t data[400];
    memset(data, 0x12, sizeof(data));
    reset();
    assert(speak(4, header, &conn) == 4);
    assert(speak(400, data, &conn) == 400);
    assert(playing && playback_ready == 1 && !notified && written == 0);
    assert(speak(4, header, &conn) == -EBUSY);
    assert(((uint16_t *) memory)[0] == 0x1212 && ((uint16_t *) memory)[1] == 0x1212);
    play_pending_block();
    assert(notified && success && written == 800 && rx_buffer == memory && conn.refs == 0);
    assert(trigger_count == 2 && triggers[0] == I2S_TRIGGER_START && triggers[1] == I2S_TRIGGER_DRAIN);
    reset();
    uint8_t tiny[] = {4, 0, 0, 0};
    assert(speak(4, tiny, &conn) == 4);
    assert(speak(4, data, &conn) == 4); // four-byte tail is data, not a new header
    play_pending_block();
    assert(written == 8 && success);
    reset();
    uint8_t too_large[] = {0x8a, 0x13, 0, 0}; // 5002 > 5000
    assert(speak(4, too_large, &conn) == -EINVAL);
    assert(speak(3, header, &conn) == -EINVAL);
    assert(speak(4, header, &conn) == 4);
    assert(speak(399, data, &conn) == -EINVAL);
    speaker_reset_stream();
    assert(current_length == 0 && offset == 0);
    for (int failure = 0; failure < 3; failure++) {
        reset();
        assert(speak(4, tiny, &conn) == 4);
        assert(speak(4, data, &conn) == 4);
        if (failure == 0)
            write_error = -EIO;
        if (failure == 1)
            trigger_error = -EIO;
        if (failure == 2)
            allocation_error = -ETIMEDOUT;
        play_pending_block();
        assert(notified && !success && conn.refs == 0);
        if (failure == 2)
            assert(rx_buffer == NULL);
    }
    puts("speaker PCM validation, DMA ownership, drain completion and error paths passed");
    return 0;
}
