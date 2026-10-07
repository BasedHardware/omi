#include "../../src/sd_card.c"
#include "connected_retention.h"

/* Run the actual queue API, append, batch commit, WAL metadata, eviction and
 * recovery against a volatile disk cache + durable image. Reset discards RAM
 * and the volatile cache. This does not model the SD chip's electrical behavior. */
int64_t test_now;
unsigned test_starts, test_stops, test_freed;
int test_wake_level;
const struct device test_device = {.name = "host-sd"};
#define HOST_SECTORS (RAW_META_SECTORS + 2U * RAW_BATCH_SECTORS)
static uint8_t disk_cache[HOST_SECTORS * DISK_SECTOR_SIZE];
static uint8_t disk_durable[sizeof(disk_cache)];
static unsigned media_syncs;
static bool fail_sync, fail_write, utc_valid = true;

bool rtc_is_valid(void)
{
    return utc_valid;
}
uint32_t get_utc_time(void)
{
    return utc_valid ? 1800000000U : 0;
}
#ifndef SD_SEM_TAKE_EXTERNAL
int k_sem_take(struct k_sem *s, int64_t timeout)
{
    (void) timeout;
    if (!s->count)
        return -EAGAIN;
    --s->count;
    return 0;
}
#endif
int k_msgq_put(struct k_msgq *q, const void *data, k_timeout_t timeout)
{
    (void) q;
    (void) timeout;
    const sd_req_t *req = data;
    assert(req->type == REQ_WRITE_DATA);
    complete_write_req(req);
    return 0;
}
int disk_access_read(const char *name, void *buf, uint32_t sector, uint32_t count)
{
    (void) name;
    assert(sector + count <= HOST_SECTORS);
    memcpy(buf, disk_cache + sector * DISK_SECTOR_SIZE, count * DISK_SECTOR_SIZE);
    return 0;
}
int disk_access_write(const char *name, const void *buf, uint32_t sector, uint32_t count)
{
    (void) name;
    assert(sector + count <= HOST_SECTORS);
    if (fail_write)
        return -EIO;
    memcpy(disk_cache + sector * DISK_SECTOR_SIZE, buf, count * DISK_SECTOR_SIZE);
    return 0;
}
int disk_access_ioctl(const char *name, unsigned command, void *out)
{
    (void) name;
    if (command == DISK_IOCTL_CTRL_SYNC) {
        if (fail_sync)
            return -EIO;
        ++media_syncs;
        memcpy(disk_durable, disk_cache, sizeof(disk_cache));
    } else if (command == DISK_IOCTL_GET_SECTOR_COUNT) {
        *(uint32_t *) out = HOST_SECTORS;
    } else if (command == DISK_IOCTL_GET_SECTOR_SIZE) {
        *(uint32_t *) out = DISK_SECTOR_SIZE;
    }
    return 0;
}

static void reboot(void)
{
    memcpy(disk_cache, disk_durable, sizeof(disk_cache));
    memset(current_batch, 0, sizeof(current_batch));
    memset(&ring_state, 0, sizeof(ring_state));
    current_batch_packets = 0;
    current_batch_loaded = current_batch_dirty = cached_read_batch_valid = false;
    meta_generation = meta_next_slot = 0;
    is_mounted = false;
    sd_write_blocked = sd_write_paused = sd_shutdown_in_progress = false;
    atomic_clear(&retention_fault);
    assert(sd_mount() == 0);
    atomic_set(&sd_boot_ready, 1);
}

static void append(uint64_t seq)
{
    uint8_t payload[CQ_PAYLOAD_BYTES], audio[] = {11, 22, 33};
    struct cq_frame frame = {.sequence = seq,
                             .captured_ms = 1800000000000ULL + 20U * seq,
                             .first_fragment = (uint16_t) seq,
                             .fragments = 1,
                             .boot_id = 42};
    assert(cq_pack(payload, audio, sizeof(audio), &frame) == 0);
    assert(sd_ring_write_retained(payload, 1800000000U) == 0);
}

int main(void)
{
    reboot();
    assert(sd_retention_ready());
    append(0);
    assert(media_syncs == 1 && ring_state.write_seq == 1);
    reboot(); /* RAM-only retention would fail here. */
    uint8_t record[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes, packets;
    assert(read_packets_internal(0, record, sizeof(record), &bytes, &packets) == 0);
    assert(bytes == sizeof(record) && packets == 1);
    struct cq_frame recovered;
    assert(cq_unpack(record + RAW_AUDIO_TIMESTAMP_BYTES, &recovered));
    assert(recovered.sequence == 0 && recovered.first_fragment == 0 && recovered.boot_id == 42);

    /* Failed SD writes/sync must not acknowledge success or advertise readiness.
     * Retrying the pending dirty tail does not consume another ring sequence. */
    uint8_t payload[CQ_PAYLOAD_BYTES], audio[] = {44, 55};
    struct cq_frame frame = {
        .sequence = 1, .captured_ms = 1800000000020ULL, .first_fragment = 1, .fragments = 1, .boot_id = 42};
    assert(cq_pack(payload, audio, sizeof(audio), &frame) == 0);
    fail_sync = true;
    assert(sd_ring_write_retained(payload, 1800000000U) == -EIO);
    assert(!sd_retention_ready());
    fail_sync = false;
    assert(sd_ring_write_retained(payload, 1800000000U) == 0);
    assert(ring_state.write_seq == 2 && sd_retention_ready());
    frame.sequence = 2;
    frame.first_fragment = 2;
    assert(cq_pack(payload, audio, sizeof(audio), &frame) == 0);
    fail_write = true;
    assert(sd_ring_write_retained(payload, 1800000000U) == -EIO);
    assert(!sd_retention_ready());
    fail_write = false;
    assert(sd_ring_write_retained(payload, 1800000000U) == 0);
    assert(ring_state.write_seq == 3);

    /* No RTC is not permission to discard connected captured audio. */
    utc_valid = false;
    frame.sequence = 3;
    frame.flags = 1;
    frame.captured_ms = 120040;
    assert(cq_pack(payload, audio, sizeof(audio), &frame) == 0);
    assert(sd_ring_write_retained(payload, 0x80000078U) == 0);
    assert(read_packets_internal(3, record, sizeof(record), &bytes, &packets) == 0);
    assert(sys_get_be32(record) == 0x80000078U);
    utc_valid = true;

    /* Two raw batch slots: overwrite evicts oldest unread WHOLE batch, and
     * persists read/write/dropped. Exercise several complete wraps. */
    for (uint64_t i = 4; i < 250; ++i) {
        append(i);
        assert(ring_state.write_seq - ring_state.read_seq <= ring_state.capacity_packets);
    }
    uint64_t oldest = ring_state.read_seq, dropped = ring_state.dropped_packets;
    assert(dropped == oldest && oldest > 0 && ring_state.write_seq == 250);
    reboot();
    assert(ring_state.read_seq == oldest && ring_state.write_seq == 250 && ring_state.dropped_packets == dropped);
    assert(read_packets_internal(oldest - 1, record, sizeof(record), &bytes, &packets) == -ERANGE);
    for (uint64_t i = oldest; i < 250; ++i) {
        assert(read_packets_internal(i, record, sizeof(record), &bytes, &packets) == 0);
        assert(cq_unpack(record + RAW_AUDIO_TIMESTAMP_BYTES, &recovered));
        assert(recovered.sequence == i && recovered.first_fragment == (uint16_t) i);
    }
    puts("Connected retention: production SD commit, failed-media retry, RTC-off, reset recovery and raw ring eviction "
         "passed");
    return 0;
}
