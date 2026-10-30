#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CONFIG_OMI_ENABLE_OFFLINE_STORAGE 1
#define CONFIG_SDMMC_VOLUME_NAME "SD:"
#define CONFIG_LOG_DEFAULT_LEVEL 0

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/pm/device.h>
#include <zephyr/random/random.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/crc.h>

#define FAKE_SECTORS (64 + 8 * 32)
static uint8_t fake_disk[FAKE_SECTORS][512];
int64_t z_stub_now_ms;

static int z_sync_fail_remaining;
static int z_sync_fail_at;
static int z_sync_call_count;
static int z_data_write_fail_remaining;
static int z_meta_write_fail_remaining;
static uint64_t z_read_fail_sectors;
static int z_read_fail_batch_calls;
static int z_rand_fail;
static uint64_t z_rand_counter;
static int z_pm_fail;
static bool z_rtc_valid;
static uint32_t z_utc;

struct op_ent {
    char kind;
    uint32_t sector;
};
static struct op_ent z_ops[4096];
static int z_ops_count;
static bool z_ops_record;

static void oplog(char kind, uint32_t sector)
{
    if (z_ops_record && z_ops_count < (int) (sizeof(z_ops) / sizeof(z_ops[0]))) {
        z_ops[z_ops_count].kind = kind;
        z_ops[z_ops_count].sector = sector;
        z_ops_count++;
    }
}

int disk_access_read(const char *pdrv, uint8_t *buf, uint32_t start, uint32_t count)
{
    (void) pdrv;
    oplog('R', start);
    for (uint32_t s = start; s < start + count; s++) {
        if ((s < 64 && (z_read_fail_sectors & (1ULL << s))) || (s >= 64 && z_read_fail_batch_calls > 0)) {
            if (s >= 64) {
                z_read_fail_batch_calls--;
            }
            return -EIO;
        }
        if (s >= FAKE_SECTORS) {
            return -EIO;
        }
        memcpy(buf + (s - start) * 512, fake_disk[s], 512);
    }
    return 0;
}

int disk_access_write(const char *pdrv, const uint8_t *buf, uint32_t start, uint32_t count)
{
    (void) pdrv;
    char kind = (start < 64) ? 'M' : 'D';
    oplog(kind, start);
    if (start < 64 && z_meta_write_fail_remaining > 0) {
        z_meta_write_fail_remaining--;
        return -EIO;
    }
    if (start >= 64 && z_data_write_fail_remaining > 0) {
        z_data_write_fail_remaining--;
        return -EIO;
    }
    for (uint32_t s = start; s < start + count; s++) {
        if (s >= FAKE_SECTORS) {
            return -EIO;
        }
        memcpy(fake_disk[s], buf + (s - start) * 512, 512);
    }
    return 0;
}

static uint32_t z_sector_count = FAKE_SECTORS;

int disk_access_ioctl(const char *pdrv, uint8_t cmd, void *buff)
{
    (void) pdrv;
    if (cmd == DISK_IOCTL_CTRL_SYNC) {
        oplog('S', 0);
        z_sync_call_count++;
        if (z_sync_fail_at > 0 && z_sync_call_count == z_sync_fail_at) {
            return -EIO;
        }
        if (z_sync_fail_remaining > 0) {
            z_sync_fail_remaining--;
            return -EIO;
        }
        return 0;
    }
    if (cmd == DISK_IOCTL_GET_SECTOR_COUNT) {
        *(uint32_t *) buff = z_sector_count;
        return 0;
    }
    if (cmd == DISK_IOCTL_GET_SECTOR_SIZE) {
        *(uint32_t *) buff = 512;
        return 0;
    }
    if (cmd == DISK_IOCTL_CTRL_INIT || cmd == DISK_IOCTL_CTRL_DEINIT) {
        return 0;
    }
    return -EINVAL;
}

int sys_csrand_get(void *dst, size_t outlen)
{
    if (z_rand_fail) {
        return -EIO;
    }
    uint8_t *b = dst;
    for (size_t i = 0; i < outlen; i++) {
        z_rand_counter += 0x9E3779B97F4A7C15ULL;
        b[i] = (uint8_t) (z_rand_counter >> (i % 8) * 8);
    }
    int allzero = 1;
    for (size_t i = 0; i < outlen; i++) {
        allzero &= (b[i] == 0);
    }
    if (allzero) {
        b[0] = 1;
    }
    return 0;
}

int gpio_pin_configure(const struct device *port, uint32_t pin, uint32_t flags)
{
    (void) port;
    (void) pin;
    (void) flags;
    return 0;
}
int gpio_pin_configure_dt(const struct gpio_dt_spec *spec, uint32_t extra_flags)
{
    (void) spec;
    (void) extra_flags;
    return 0;
}
int gpio_pin_set_dt(const struct gpio_dt_spec *spec, int value)
{
    (void) spec;
    (void) value;
    return 0;
}
int gpio_pin_set_raw(const struct device *port, uint32_t pin, int value)
{
    (void) port;
    (void) pin;
    (void) value;
    return 0;
}
int pm_device_action_run(const struct device *dev, enum pm_device_action action)
{
    (void) dev;
    (void) action;
    return z_pm_fail;
}

struct device z_stub_dev_sdhc0 = {"sdhc0"};
struct device z_stub_dev_gpio1 = {"gpio1"};
struct device z_stub_dev_spi3 = {"spi3"};
struct device z_stub_dev_sdcard_en_pin = {"sd_en"};

static int z_marks_count;
static struct {
    uint64_t ring_id;
    uint64_t ring_seq;
    uint16_t live_index;
    uint32_t session;
} z_marks[64];
void storage_queue_live_mark(uint64_t ring_id, uint64_t ring_seq, uint16_t live_index, uint32_t session)
{
    if (z_marks_count < (int) (sizeof(z_marks) / sizeof(z_marks[0]))) {
        z_marks[z_marks_count].ring_id = ring_id;
        z_marks[z_marks_count].ring_seq = ring_seq;
        z_marks[z_marks_count].live_index = live_index;
        z_marks[z_marks_count].session = session;
        z_marks_count++;
    }
}

bool rtc_is_valid(void)
{
    return z_rtc_valid;
}
uint32_t get_utc_time(void)
{
    return z_utc;
}

#include "../src/sd_card.c"

static int failures;
#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        if (!(cond)) {                                                                                                 \
            printf("FAIL %d: %s\n", __LINE__, #cond);                                                                  \
            failures++;                                                                                                \
        }                                                                                                              \
    } while (0)

static void disk_reset(void)
{
    memset(fake_disk, 0, sizeof(fake_disk));
    z_sync_fail_remaining = 0;
    z_sync_fail_at = 0;
    z_sync_call_count = 0;
    z_data_write_fail_remaining = 0;
    z_meta_write_fail_remaining = 0;
    z_read_fail_sectors = 0;
    z_read_fail_batch_calls = 0;
    z_rand_fail = 0;
    z_pm_fail = 0;
    z_rtc_valid = false;
    z_utc = 0;
    z_ops_count = 0;
    z_marks_count = 0;
    z_sector_count = FAKE_SECTORS;
}

static void ram_reset(void)
{
    is_mounted = false;
    pending_commit_valid = false;
    current_batch_loaded = false;
    current_batch_packets = 0;
    current_batch_dirty = false;
    cached_read_batch_valid = false;
    live_eval_count = 0;
    omi_live_mark_reset(&live_mark_state);
    sd_write_blocked = false;
    ring_state.capacity_packets = 0;
}

static void write_v1_meta(uint32_t slot, uint64_t gen, uint64_t read_seq, uint64_t write_seq)
{
    struct raw_meta_record rec = {0};
    rec.magic = RAW_META_MAGIC;
    rec.version = RAW_LAYOUT_VERSION;
    rec.generation = gen;
    rec.read_seq = read_seq;
    rec.write_seq = write_seq;
    memcpy(fake_disk[slot], &rec, sizeof(rec));
}

static void
write_v2_meta(uint32_t slot, uint64_t gen, uint64_t read_seq, uint64_t write_seq, uint64_t ring_id, uint64_t data_id)
{
    struct raw_meta_record rec = {0};
    rec.magic = RAW_META_MAGIC;
    rec.version = RAW_META_VERSION;
    rec.generation = gen;
    rec.read_seq = read_seq;
    rec.write_seq = write_seq;
    rec.ring_id = ring_id;
    rec.data_id = data_id;
    rec.crc32 = crc32_ieee((const uint8_t *) &rec, offsetof(struct raw_meta_record, crc32));
    memcpy(fake_disk[slot], &rec, sizeof(rec));
}

static void
write_batch(uint64_t base_seq, uint16_t version, uint64_t gen, uint16_t packets, uint64_t data_id, uint8_t tag)
{
    uint32_t sector = RAW_META_SECTORS + (uint32_t) ((base_seq / RAW_PACKETS_PER_BATCH) % 8) * RAW_BATCH_SECTORS;
    memset(fake_disk + sector, tag, RAW_BATCH_SECTORS * 512);
    struct raw_batch_header h = {0};
    h.magic = RAW_BATCH_MAGIC;
    h.version = version;
    h.packet_count = packets;
    h.generation = gen;
    h.start_seq = base_seq;
    h.data_id_lo = (uint32_t) (data_id & UINT32_MAX);
    h.data_id_hi = (uint32_t) (data_id >> 32);
    memcpy(fake_disk[sector], &h, sizeof(h));
}

static void push_records(uint16_t packets, uint8_t tag, uint32_t session, uint16_t index)
{
    sd_req_t req = {0};
    req.type = REQ_WRITE_DATA;
    req.u.write.len = MAX_WRITE_SIZE;
    memset(req.u.write.buf, tag, MAX_WRITE_SIZE);
    req.u.write.live_session = session;
    req.u.write.live_index = index;
    for (uint16_t i = 0; i < packets; i++) {
        process_write_data_req(&req);
    }
}

static void reboot(void)
{
    ram_reset();
    int ret = sd_mount();
    CHECK(ret == 0);
}

static void test_fresh_mount(void)
{
    disk_reset();
    ram_reset();
    CHECK(sd_mount() == 0);
    CHECK(ring_state.ring_id != 0);
    CHECK(ring_data_id != 0);
    CHECK(ring_state.write_seq == 0);
    uint64_t id = ring_state.ring_id;
    reboot();
    CHECK(ring_state.ring_id == id);
    printf("fresh_mount ok\n");
}

static void test_v1_migration(void)
{
    disk_reset();
    ram_reset();
    write_v1_meta(0, 5, 0, 40);
    write_batch(0, RAW_LAYOUT_VERSION, 4, 36, 0, 0x5A);
    write_batch(36, RAW_LAYOUT_VERSION, 5, 4, 0, 0x33);
    CHECK(sd_mount() == 0);
    CHECK(ring_state.ring_id != 0);
    CHECK(ring_data_id != 0);
    CHECK(ring_state.write_seq == 40);
    uint64_t id = ring_state.ring_id;
    uint8_t buf[RAW_AUDIO_PACKET_BYTES * 4];
    uint32_t bytes = 0, packets = 0;
    CHECK(read_packets_internal(36, buf, sizeof(buf), &bytes, &packets) == 0);
    CHECK(packets == 4);
    CHECK(buf[4] == 0x33);
    reboot();
    CHECK(ring_state.ring_id == id);
    CHECK(ring_state.write_seq == 40);
    printf("v1_migration ok\n");
}

static void test_clear_rotates_ids(void)
{
    disk_reset();
    ram_reset();
    CHECK(sd_mount() == 0);
    uint64_t old_id = ring_state.ring_id;
    uint64_t old_data_id = ring_data_id;
    CHECK(clear_ring_internal(false) == 0);
    CHECK(ring_state.ring_id != old_id);
    CHECK(ring_data_id != old_data_id);
    CHECK(advance_read_seq_internal(0, old_id, true) == -ESTALE);
    CHECK(advance_read_seq_internal(5, old_id, true) == -ESTALE);
    printf("clear_rotates ok\n");
}

static void test_commit_order(void)
{
    disk_reset();
    ram_reset();
    CHECK(sd_mount() == 0);
    z_ops_count = 0;
    z_ops_record = true;
    push_records(2, 0x11, 0, 0);
    CHECK(flush_current_batch(true) == 0);
    z_ops_record = false;
    int di = -1, s1 = -1, mi = -1, s2 = -1;
    for (int i = 0; i < z_ops_count; i++) {
        if (z_ops[i].kind == 'D' && di < 0) {
            di = i;
        }
        if (z_ops[i].kind == 'S' && di >= 0 && s1 < 0) {
            s1 = i;
        }
        if (z_ops[i].kind == 'M' && s1 >= 0 && mi < 0) {
            mi = i;
        }
        if (z_ops[i].kind == 'S' && mi >= 0) {
            s2 = i;
        }
    }
    CHECK(di >= 0 && s1 > di && mi > s1 && s2 > mi);
    printf("commit_order ok\n");
}

static void test_commit_failures(void)
{
    for (int stage = 0; stage < 4; stage++) {
        disk_reset();
        ram_reset();
        CHECK(sd_mount() == 0);
        push_records(3, 0x77, 7, 42);
        uint64_t ws_before = ring_state.write_seq;
        switch (stage) {
        case 0:
            z_data_write_fail_remaining = 1;
            break;
        case 1:
            z_sync_fail_at = z_sync_call_count + 1;
            break;
        case 2:
            z_meta_write_fail_remaining = 1;
            break;
        case 3:
            z_sync_fail_at = z_sync_call_count + 2;
            break;
        }
        int ret = flush_current_batch(true);
        CHECK(ret < 0);
        CHECK(ring_state.write_seq == ws_before);
        CHECK(current_batch_dirty);
        CHECK(z_marks_count == 0);
        CHECK(flush_current_batch(true) == 0);
        CHECK(ring_state.write_seq == ws_before + 3);
        CHECK(!current_batch_dirty);
        CHECK(z_marks_count == 1);
        CHECK(z_marks[0].ring_seq == ws_before + 3);
        CHECK(z_marks[0].live_index == 42);
        CHECK(z_marks[0].session == 7);
        z_marks_count = 0;
    }
    printf("commit_failures ok\n");
}

static void test_pending_meta_sync_clear(void)
{
    disk_reset();
    ram_reset();
    CHECK(sd_mount() == 0);
    uint64_t old_id = ring_state.ring_id;
    z_sync_fail_remaining = 1;
    CHECK(clear_ring_internal(false) < 0);
    CHECK(pending_commit_valid);
    CHECK(ring_state.ring_id == old_id);
    z_sync_fail_remaining = 1;
    CHECK(advance_read_seq_internal(0, old_id, true) == -EIO);
    CHECK(pending_commit_valid);
    CHECK(advance_read_seq_internal(0, old_id, true) == -ESTALE);
    CHECK(!pending_commit_valid);
    reboot();
    uint64_t newest_id = 0;
    uint64_t newest_gen = 0;
    for (uint32_t s = 0; s < RAW_META_SECTORS; s++) {
        struct raw_meta_record r;
        memcpy(&r, fake_disk[s], sizeof(r));
        if (r.magic == RAW_META_MAGIC && r.version == RAW_META_VERSION && r.generation > newest_gen) {
            newest_gen = r.generation;
            newest_id = r.ring_id;
        }
    }
    CHECK(newest_id != 0 && newest_id != old_id);
    CHECK(ring_state.ring_id == newest_id);
    CHECK(advance_read_seq_internal(3, old_id, true) == -ESTALE);
    printf("pending_meta_sync ok\n");
}

static void test_pending_retry(void)
{
    disk_reset();
    ram_reset();
    CHECK(sd_mount() == 0);
    push_records(1, 0x42, 7, 42);
    z_sync_fail_at = z_sync_call_count + 2;
    int ret = flush_current_batch(true);
    CHECK(ret < 0);
    CHECK(pending_commit_valid);
    CHECK(current_batch_dirty);
    CHECK(ring_state.write_seq == 0);
    CHECK(z_marks_count == 0);
    ret = flush_current_batch(true);
    CHECK(ret == 0);
    CHECK(!pending_commit_valid);
    CHECK(ring_state.write_seq == 1);
    CHECK(z_marks_count == 1);
    CHECK(z_marks[0].ring_seq == 1);
    CHECK(z_marks[0].live_index == 42);
    CHECK(z_marks[0].session == 7);
    printf("pending_retry ok\n");
}

static void test_suspect_rotation_keeps_audio(void)
{
    disk_reset();
    ram_reset();
    write_v2_meta(0, 10, 0, 36, 0xABCDEF01ULL, 0x12345678ULL);
    struct raw_meta_record torn = {0};
    torn.magic = RAW_META_MAGIC;
    torn.version = RAW_META_VERSION;
    torn.generation = 11;
    torn.write_seq = 36;
    torn.ring_id = 0xABCDEF01ULL;
    torn.data_id = 0x12345678ULL;
    torn.crc32 = 0xDEADBEEF;
    memcpy(fake_disk[1], &torn, sizeof(torn));
    write_batch(0, RAW_BATCH_VERSION, 9, 36, 0x12345678ULL, 0x66);
    CHECK(sd_mount() == 0);
    CHECK(ring_state.ring_id != 0xABCDEF01ULL);
    CHECK(ring_data_id == 0x12345678ULL);
    CHECK(ring_state.write_seq == 36);
    uint8_t buf[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes = 0, packets = 0;
    CHECK(read_packets_internal(0, buf, sizeof(buf), &bytes, &packets) == 0);
    CHECK(packets == 1 && buf[4] == 0x66);
    disk_reset();
    ram_reset();
    write_v2_meta(0, 10, 0, 36, 0xABCDEF01ULL, 0x12345678ULL);
    torn.generation = 3;
    memcpy(fake_disk[40], &torn, sizeof(torn));
    CHECK(sd_mount() == 0);
    CHECK(ring_state.ring_id == 0xABCDEF01ULL);
    printf("suspect_rotation ok\n");
}

static void test_data_ahead_of_metadata(void)
{
    disk_reset();
    ram_reset();
    write_v2_meta(0, 10, 0, 36, 0xABCDEF02ULL, 0x12345679ULL);
    write_batch(0, RAW_BATCH_VERSION, 9, 36, 0x12345679ULL, 0x66);
    write_batch(36, RAW_BATCH_VERSION, 11, 36, 0x12345679ULL, 0x77);
    CHECK(sd_mount() == 0);
    CHECK(ring_state.ring_id != 0xABCDEF02ULL);
    CHECK(ring_data_id == 0x12345679ULL);
    CHECK(ring_state.write_seq == 72);
    uint8_t buf[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes = 0, packets = 0;
    CHECK(read_packets_internal(36, buf, sizeof(buf), &bytes, &packets) == 0);
    CHECK(packets == 1 && buf[4] == 0x77);
    push_records(1, 0x88, 0, 0);
    CHECK(flush_current_batch(false) == 0);
    CHECK(ring_state.write_seq == 73);
    CHECK(fake_disk[96][32 + 4] == 0x77);
    bytes = packets = 0;
    CHECK(read_packets_internal(72, buf, sizeof(buf), &bytes, &packets) == 0);
    CHECK(packets == 1 && buf[4] == 0x88);
    printf("data_ahead ok\n");
}

static void test_torn_newer_data_ahead(void)
{
    disk_reset();
    ram_reset();
    write_v2_meta(0, 10, 0, 36, 0xABCDEF04ULL, 0x12345681ULL);
    write_v2_meta(1, 11, 0, 36, 0x9999ULL, 0x12345681ULL);
    fake_disk[1][offsetof(struct raw_meta_record, crc32)] ^= 0xFF;
    write_batch(0, RAW_BATCH_VERSION, 10, 36, 0x12345681ULL, 0x66);
    write_batch(36, RAW_BATCH_VERSION, 11, 36, 0x12345681ULL, 0x77);
    CHECK(sd_mount() == 0);
    CHECK(ring_state.ring_id != 0xABCDEF04ULL);
    CHECK(ring_state.ring_id != 0x9999ULL);
    CHECK(ring_data_id == 0x12345681ULL);
    CHECK(ring_state.write_seq == 72);
    uint8_t buf[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes = 0, packets = 0;
    CHECK(read_packets_internal(36, buf, sizeof(buf), &bytes, &packets) == 0);
    CHECK(packets == 1 && buf[4] == 0x77);
    bytes = packets = 0;
    CHECK(read_packets_internal(0, buf, sizeof(buf), &bytes, &packets) == 0);
    CHECK(packets == 1 && buf[4] == 0x66);
    printf("torn_newer_data_ahead ok\n");
}

static void test_transient_tail_read(void)
{
    disk_reset();
    ram_reset();
    write_v2_meta(0, 10, 0, 38, 0xABCDEF05ULL, 0x12345682ULL);
    write_batch(0, RAW_BATCH_VERSION, 9, 36, 0x12345682ULL, 0x66);
    write_batch(36, RAW_BATCH_VERSION, 10, 2, 0x12345682ULL, 0x99);
    z_read_fail_batch_calls = 1;
    CHECK(sd_mount() == -EIO);
    CHECK(!is_mounted);
    CHECK(fake_disk[1][0] == 0);
    CHECK(sd_mount() == 0);
    CHECK(ring_state.ring_id == 0xABCDEF05ULL);
    CHECK(ring_state.write_seq == 38);
    uint8_t buf[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes = 0, packets = 0;
    CHECK(read_packets_internal(36, buf, sizeof(buf), &bytes, &packets) == 0);
    CHECK(packets == 1 && buf[4] == 0x99);
    printf("transient_tail_read ok\n");
}

static void test_tail_count_rollback(void)
{
    disk_reset();
    ram_reset();
    write_v2_meta(0, 10, 0, 40, 0xABCDEF03ULL, 0x12345680ULL);
    write_batch(0, RAW_BATCH_VERSION, 9, 36, 0x12345680ULL, 0x66);
    write_batch(36, RAW_BATCH_VERSION, 10, 2, 0x12345680ULL, 0x99);
    CHECK(sd_mount() == 0);
    CHECK(ring_state.ring_id != 0xABCDEF03ULL);
    CHECK(ring_state.write_seq == 38);
    CHECK(ring_data_id == 0x12345680ULL);
    uint8_t buf[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes = 0, packets = 0;
    CHECK(read_packets_internal(0, buf, sizeof(buf), &bytes, &packets) == 0);
    CHECK(packets == 1 && buf[4] == 0x66);
    bytes = packets = 0;
    CHECK(read_packets_internal(36, buf, sizeof(buf), &bytes, &packets) == 0);
    CHECK(packets == 1 && buf[4] == 0x99);
    printf("tail_rollback ok\n");
}

static void test_pending_clear_undo(void)
{
    disk_reset();
    ram_reset();
    CHECK(sd_mount() == 0);
    uint64_t old_id = ring_state.ring_id;
    uint64_t old_data_id = ring_data_id;
    push_records(3, 0x51, 0, 0);
    z_sync_fail_remaining = 1;
    CHECK(clear_ring_internal(false) < 0);
    CHECK(pending_commit_valid);
    CHECK(ring_state.ring_id == old_id);
    CHECK(current_batch_dirty);
    CHECK(flush_current_batch(true) == 0);
    CHECK(!pending_commit_valid);
    CHECK(ring_state.ring_id != old_id);
    CHECK(ring_data_id != old_data_id);
    CHECK(ring_state.write_seq == 0);
    CHECK(!current_batch_dirty);
    CHECK(current_batch_packets == 0);
    CHECK(advance_read_seq_internal(1, old_id, true) == -ESTALE);
    uint8_t buf[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes = 0, packets = 0;
    CHECK(read_packets_internal(1, buf, sizeof(buf), &bytes, &packets) == -ERANGE);
    push_records(1, 0x52, 0, 0);
    CHECK(flush_current_batch(false) == 0);
    CHECK(ring_state.write_seq == 1);
    bytes = packets = 0;
    CHECK(read_packets_internal(0, buf, sizeof(buf), &bytes, &packets) == 0);
    CHECK(buf[4] == 0x52);
    struct raw_batch_header h;
    memcpy(&h, fake_disk[64], sizeof(h));
    CHECK(batch_header_data_id(&h) == ring_data_id);
    printf("pending_clear_undo ok\n");
}

static void test_full_dirty_batch_retained(void)
{
    disk_reset();
    ram_reset();
    CHECK(sd_mount() == 0);
    push_records(RAW_PACKETS_PER_BATCH - 1, 0x21, 0, 0);
    z_data_write_fail_remaining = 2;
    push_records(2, 0x22, 0, 0);
    CHECK(current_batch_packets == RAW_PACKETS_PER_BATCH);
    CHECK(current_batch_dirty);
    CHECK(flush_current_batch(true) == 0);
    CHECK(ring_state.write_seq == RAW_PACKETS_PER_BATCH);
    uint8_t buf[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes = 0, packets = 0;
    CHECK(read_packets_internal(0, buf, sizeof(buf), &bytes, &packets) == 0);
    CHECK(buf[4] == 0x21);
    printf("full_dirty ok\n");
}

static void test_poweroff_drain_retention(void)
{
    disk_reset();
    ram_reset();
    CHECK(sd_mount() == 0);
    push_records(1, 0x61, 0, 0);
    z_sync_fail_at = z_sync_call_count + 2;
    CHECK(flush_current_batch(true) < 0);
    CHECK(pending_commit_valid);
    sd_req_t w = {0};
    w.type = REQ_WRITE_DATA;
    w.u.write.len = MAX_WRITE_SIZE;
    for (uint32_t i = 0; i < 4U; i++) {
        memset(w.u.write.buf, 0x62 + i, MAX_WRITE_SIZE);
        CHECK(k_msgq_put(&sd_msgq, &w, K_NO_WAIT) == 0);
    }
    z_sync_fail_remaining = 1;
    CHECK(drain_pending_write_queue_for_shutdown() < 0);
    CHECK(k_msgq_num_used_get(&sd_msgq) == 4);
    CHECK(pending_commit_valid);
    CHECK(drain_pending_write_queue_for_shutdown() == 0);
    CHECK(k_msgq_num_used_get(&sd_msgq) == 0);
    CHECK(ring_state.write_seq == 1);
    CHECK(current_batch_packets == 5);
    CHECK(current_batch_dirty);
    printf("poweroff_drain ok\n");
}

static void test_ring_full_overwrite(void)
{
    disk_reset();
    ram_reset();
    CHECK(sd_mount() == 0);
    uint64_t cap = ring_state.capacity_packets;
    for (uint64_t i = 0; i < cap + RAW_PACKETS_PER_BATCH; i++) {
        push_records(1, (uint8_t) i, 0, 0);
        if ((i % RAW_PACKETS_PER_BATCH) == RAW_PACKETS_PER_BATCH - 1) {
            CHECK(flush_current_batch(false) == 0);
        }
    }
    CHECK(flush_current_batch(false) == 0);
    CHECK(ring_state.write_seq == cap + RAW_PACKETS_PER_BATCH);
    CHECK(ring_state.read_seq == RAW_PACKETS_PER_BATCH);
    CHECK(ring_state.dropped_packets == RAW_PACKETS_PER_BATCH);
    CHECK(ring_state.capacity_packets == cap);
    printf("ring_full ok\n");
}

static void test_rtc_flag(void)
{
    disk_reset();
    ram_reset();
    CHECK(sd_mount() == 0);
    z_stub_now_ms = 65000;
    push_records(1, 0x55, 0, 0);
    CHECK(flush_current_batch(false) == 0);
    uint8_t buf[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes = 0, packets = 0;
    CHECK(read_packets_internal(0, buf, sizeof(buf), &bytes, &packets) == 0);
    uint32_t ts = sys_get_be32(buf);
    CHECK((ts & OMI_TS_FLAG_UPTIME) != 0);
    CHECK((ts & OMI_TS_VALUE_MASK) == 65);
    printf("rtc_flag ok\n");
}

static void test_advance_rules(void)
{
    disk_reset();
    ram_reset();
    CHECK(sd_mount() == 0);
    push_records(5, 0x31, 0, 0);
    CHECK(flush_current_batch(false) == 0);
    CHECK(advance_read_seq_internal(2, ring_state.ring_id, true) == 0);
    CHECK(ring_state.read_seq == 2);
    CHECK(advance_read_seq_internal(2, ring_state.ring_id, true) == 0);
    CHECK(advance_read_seq_internal(1, ring_state.ring_id, true) == 0);
    CHECK(advance_read_seq_internal(99, ring_state.ring_id, true) == -ERANGE);
    CHECK(advance_read_seq_internal(3, ring_state.ring_id + 1, true) == -ESTALE);
    CHECK(ring_state.read_seq == 2);
    printf("advance_rules ok\n");
}

int main(void)
{
    test_fresh_mount();
    test_v1_migration();
    test_clear_rotates_ids();
    test_commit_order();
    test_commit_failures();
    test_pending_meta_sync_clear();
    test_pending_retry();
    test_suspect_rotation_keeps_audio();
    test_data_ahead_of_metadata();
    test_torn_newer_data_ahead();
    test_transient_tail_read();
    test_tail_count_rollback();
    test_pending_clear_undo();
    test_full_dirty_batch_retained();
    test_poweroff_drain_retention();
    test_ring_full_overwrite();
    test_rtc_flag();
    test_advance_rules();
    printf("sd_card harness: %d failures\n", failures);
    return failures ? 1 : 0;
}
