#include "lib/core/sd_card.h"

#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device.h>
#include <zephyr/random/random.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/crc.h>
#include <zephyr/sys/util.h>

#include "lib/core/custody.h"
#include "lib/core/storage.h"
#include "rtc.h"

LOG_MODULE_REGISTER(sd_card, CONFIG_LOG_DEFAULT_LEVEL);

#define DISK_DRIVE_NAME CONFIG_SDMMC_VOLUME_NAME
#define DISK_SECTOR_SIZE 512U

#define SD_REQ_QUEUE_MSGS 100
#define SD_PRIO_QUEUE_MSGS 10
#define WRITE_DRAIN_BURST 16

#define RAW_META_SECTORS 64U
#define RAW_BATCH_SECTORS 32U
#define RAW_BATCH_BYTES (RAW_BATCH_SECTORS * DISK_SECTOR_SIZE)
#define RAW_BATCH_HEADER_BYTES 32U
#define RAW_PACKETS_PER_BATCH ((RAW_BATCH_BYTES - RAW_BATCH_HEADER_BYTES) / RAW_AUDIO_PACKET_BYTES)
#define RAW_FLUSH_INTERVAL_MS 1000

#define RAW_META_MAGIC 0x4F4D4952U
#define RAW_BATCH_MAGIC 0x4F4D4942U
#define RAW_META_VERSION 2U
#define RAW_LAYOUT_VERSION 1U
#define RAW_BATCH_VERSION 2U

#define ERROR_THRESHOLD 5

BUILD_ASSERT((RAW_BATCH_HEADER_BYTES + RAW_PACKETS_PER_BATCH * RAW_AUDIO_PACKET_BYTES) <= RAW_BATCH_BYTES,
             "raw batch layout exceeds batch size");

struct raw_meta_record {
    uint32_t magic;
    uint16_t version;
    uint16_t reserved0;
    uint64_t generation;
    uint64_t read_seq;
    uint64_t write_seq;
    uint64_t dropped_packets;
    uint64_t ring_id;
    uint64_t data_id;
    uint32_t crc32;
    uint32_t reserved1;
};

struct raw_batch_header {
    uint32_t magic;
    uint16_t version;
    uint16_t packet_count;
    uint64_t generation;
    uint64_t start_seq;
    uint32_t data_id_lo;
    uint32_t data_id_hi;
};

struct read_resp {
    struct k_sem sem;
    atomic_t *busy_flag;
    int res;
    uint32_t bytes_read;
    uint32_t packets_read;
};

struct status_resp {
    struct k_sem sem;
    atomic_t *busy_flag;
    int res;
};

struct info_resp {
    struct k_sem sem;
    atomic_t *busy_flag;
    int res;
    sd_ring_info_t info;
};

static void release_resp_busy(atomic_t *busy_flag)
{
    if (busy_flag) {
        atomic_clear(busy_flag);
    }
}

static int wait_for_sd_worker_response(struct k_sem *sem, int timeout_ms, const char *op_name)
{
    if (!sem || !op_name) {
        return -EINVAL;
    }

    if (k_sem_take(sem, K_MSEC(timeout_ms)) == 0) {
        return 0;
    }

    LOG_WRN("%s timed out after %d ms waiting for SD worker; subsequent calls may return -EBUSY until the pending "
            "request completes",
            op_name,
            timeout_ms);
    return -ETIMEDOUT;
}

typedef enum {
    REQ_WRITE_DATA,
    REQ_GET_RING_INFO,
    REQ_READ_PACKETS,
    REQ_ADVANCE_READ,
    REQ_CLEAR_RING,
    REQ_FLUSH,
    REQ_UNMOUNT,
    REQ_POWER_OFF, /* flush + unmount + cut SD power (idle) */
    REQ_POWER_ON,  /* power on + remount (mic wake) */
} sd_req_type_t;

typedef struct {
    sd_req_type_t type;
    union {
        struct {
            uint8_t buf[MAX_WRITE_SIZE];
            size_t len;
            uint32_t live_session;
            uint16_t live_index;
        } write;
        struct {
            uint64_t start_seq;
            uint32_t max_bytes;
            uint8_t *out_buf;
            struct read_resp *resp;
        } read;
        struct {
            uint64_t new_read_seq;
            uint64_t ring_id;
            bool check_id;
            struct status_resp *resp;
        } advance;
        struct {
            struct info_resp *resp;
        } info;
        struct {
            struct status_resp *resp;
        } status;
    } u;
} sd_req_t;

static const struct device *const sd_dev = DEVICE_DT_GET(DT_NODELABEL(sdhc0));
static const struct gpio_dt_spec sd_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

K_MSGQ_DEFINE(sd_msgq, sizeof(sd_req_t), SD_REQ_QUEUE_MSGS, 4);
K_MSGQ_DEFINE(sd_prio_msgq, sizeof(sd_req_t), SD_PRIO_QUEUE_MSGS, 4);

#define SD_WORKER_STACK_SIZE 8192
#define SD_WORKER_PRIORITY 7
K_THREAD_STACK_DEFINE(sd_worker_stack, SD_WORKER_STACK_SIZE);
static struct k_thread sd_worker_thread_data;
static k_tid_t sd_worker_tid;

static atomic_t sd_boot_ready;
static atomic_t sd_io_low_power = ATOMIC_INIT(0);
static atomic_t sd_dev_pm_supported = ATOMIC_INIT(1);
static atomic_t pending_flush_on_ble_connect;

static bool is_mounted;
static bool sd_enabled;
static bool sd_shutdown_in_progress;
static bool sd_write_blocked;
static bool sd_write_paused;
static bool ble_connected;

static uint32_t disk_sector_count;
static uint32_t data_batch_count;
static uint32_t meta_next_slot;
static uint64_t meta_generation;
static uint64_t recovery_generation;
static sd_ring_info_t ring_state;
static uint64_t ring_data_id;

static uint8_t current_batch[RAW_BATCH_BYTES];
static uint8_t batch_read_buffer[RAW_BATCH_BYTES];
static uint8_t sector_buffer[DISK_SECTOR_SIZE];
static uint16_t current_batch_packets;
static uint64_t current_batch_base_seq;
static uint64_t cached_read_batch_base_seq = UINT64_MAX;
static struct raw_batch_header cached_read_batch_header;
static bool current_batch_loaded;
static bool current_batch_dirty;
static bool cached_read_batch_valid;
static int64_t batch_dirty_since_ms;
static uint8_t writing_error_counter;
static uint32_t sd_write_drop_count;

static uint32_t batch_live_session[RAW_PACKETS_PER_BATCH];
static uint16_t batch_live_index[RAW_PACKETS_PER_BATCH];
static uint16_t live_eval_count;
static omi_live_mark_t live_mark_state;

static uint32_t write_drop_packets;
static uint32_t write_drop_bytes;
static int64_t last_write_blocked_log_ms;

static char compat_current_name[MAX_FILENAME_LEN];
static char compat_saved_name[MAX_FILENAME_LEN];
static uint32_t compat_saved_offset;

static void sd_worker_thread(void);
static void sd_set_io_low_power(bool enable);
static int flush_current_batch(bool sync_media);
static void live_mark_eval_committed(void);

static void invalidate_read_batch_cache(void)
{
    cached_read_batch_valid = false;
    cached_read_batch_base_seq = UINT64_MAX;
}

static bool pm_action_is_unsupported(int ret)
{
    return (ret == -ENOSYS || ret == -ENOTSUP);
}

static bool pm_action_is_ok(int ret)
{
    return (ret == 0 || ret == -EALREADY || pm_action_is_unsupported(ret));
}

static void format_timestamp_name(uint32_t timestamp, char *buf, size_t buf_size)
{
    if (!buf || buf_size == 0U) {
        return;
    }

    snprintk(buf, buf_size, "%08X.txt", timestamp);
}

static uint64_t ring_used_packets(void)
{
    uint64_t committed = ring_state.write_seq - ring_state.read_seq;

    if (!current_batch_loaded || current_batch_packets == 0U) {
        return committed;
    }

    if (current_batch_base_seq + current_batch_packets <= ring_state.write_seq) {
        return committed;
    }

    return committed + (current_batch_base_seq + current_batch_packets - ring_state.write_seq);
}

static uint64_t ring_used_bytes(void)
{
    return ring_used_packets() * RAW_AUDIO_PACKET_BYTES;
}

static uint32_t batch_sector_for_base_seq(uint64_t base_seq)
{
    uint64_t batch_index = base_seq / RAW_PACKETS_PER_BATCH;
    uint32_t slot = (uint32_t) (batch_index % data_batch_count);
    return RAW_META_SECTORS + (slot * RAW_BATCH_SECTORS);
}

static void start_empty_batch(uint64_t base_seq)
{
    memset(current_batch, 0, sizeof(current_batch));
    memset(batch_live_session, 0, sizeof(batch_live_session));
    memset(batch_live_index, 0, sizeof(batch_live_index));
    live_eval_count = 0;
    current_batch_base_seq = base_seq;
    current_batch_packets = 0;
    current_batch_loaded = true;
    current_batch_dirty = false;
}

static int sync_media(void)
{
    return disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_SYNC, NULL);
}

static int ring_generate_id(uint64_t *out)
{
    if (!out) {
        return -EINVAL;
    }

    for (int attempt = 0; attempt < 4; attempt++) {
        uint64_t id = 0;
        int ret = sys_csrand_get(&id, sizeof(id));
        if (ret == 0 && id != 0U) {
            *out = id;
            return 0;
        }
    }

    LOG_ERR("hardware RNG failed: cannot mint ring_id");
    return -EIO;
}

static uint32_t meta_record_crc(const struct raw_meta_record *record)
{
    return crc32_ieee((const uint8_t *) record, offsetof(struct raw_meta_record, crc32));
}

static bool meta_record_valid(const struct raw_meta_record *record)
{
    if (!record) {
        return false;
    }

    if (record->magic != RAW_META_MAGIC) {
        return false;
    }

    if (record->version == RAW_META_VERSION) {
        if (record->ring_id == 0U || record->data_id == 0U || record->crc32 != meta_record_crc(record)) {
            return false;
        }
    } else if (record->version != RAW_LAYOUT_VERSION) {
        return false;
    }

    if (record->write_seq < record->read_seq) {
        return false;
    }

    if ((record->write_seq - record->read_seq) > ring_state.capacity_packets) {
        return false;
    }

    return true;
}

static uint64_t batch_header_data_id(const struct raw_batch_header *header)
{
    return ((uint64_t) header->data_id_hi << 32) | header->data_id_lo;
}

static bool batch_header_valid(const struct raw_batch_header *header)
{
    if (!header) {
        return false;
    }

    if (header->magic != RAW_BATCH_MAGIC) {
        return false;
    }

    if (header->version != RAW_LAYOUT_VERSION && header->version != RAW_BATCH_VERSION) {
        return false;
    }

    if (header->version == RAW_BATCH_VERSION && ring_data_id != 0U && batch_header_data_id(header) != ring_data_id) {
        return false;
    }

    if (header->packet_count > RAW_PACKETS_PER_BATCH) {
        return false;
    }

    if ((header->start_seq % RAW_PACKETS_PER_BATCH) != 0U) {
        return false;
    }

    return true;
}

static int write_journal_record(const sd_ring_info_t *state, uint64_t data_id)
{
    struct raw_meta_record record = {
        .magic = RAW_META_MAGIC,
        .version = RAW_META_VERSION,
        .generation = ++meta_generation,
        .read_seq = state->read_seq,
        .write_seq = state->write_seq,
        .dropped_packets = state->dropped_packets,
        .ring_id = state->ring_id,
        .data_id = data_id,
    };
    record.crc32 = meta_record_crc(&record);

    memset(sector_buffer, 0, sizeof(sector_buffer));
    memcpy(sector_buffer, &record, sizeof(record));

    int ret = disk_access_write(DISK_DRIVE_NAME, sector_buffer, meta_next_slot, 1);
    if (ret != 0) {
        LOG_ERR("metadata write failed at slot %u: %d", meta_next_slot, ret);
        meta_generation--;
        return -EIO;
    }

    meta_next_slot = (meta_next_slot + 1U) % RAW_META_SECTORS;
    return 0;
}

static bool pending_commit_valid;
static sd_ring_info_t pending_commit_state;
static uint64_t pending_commit_data_id;
static bool pending_commit_clear;

static void publish_committed_state(const sd_ring_info_t *state, uint64_t data_id, bool is_clear)
{
    ring_state = *state;
    ring_data_id = data_id;

    if (is_clear) {
        compat_current_name[0] = '\0';
        compat_saved_name[0] = '\0';
        compat_saved_offset = 0;
        invalidate_read_batch_cache();
        omi_live_mark_reset(&live_mark_state);
        start_empty_batch(0);
    }
}

static int resolve_pending_commit(void)
{
    int ret = sync_media();
    if (ret != 0) {
        LOG_ERR("pending metadata media sync retry failed: %d", ret);
        return -EIO;
    }

    bool finalize_batch = !pending_commit_clear && current_batch_dirty &&
                          pending_commit_state.write_seq == current_batch_base_seq + current_batch_packets;

    pending_commit_valid = false;
    publish_committed_state(&pending_commit_state, pending_commit_data_id, pending_commit_clear);

    if (finalize_batch) {
        current_batch_dirty = false;
        invalidate_read_batch_cache();
        writing_error_counter = 0;
        live_mark_eval_committed();
        if (current_batch_packets >= RAW_PACKETS_PER_BATCH) {
            start_empty_batch(ring_state.write_seq);
        }
    }
    return 0;
}

static int ensure_pending_resolved(void)
{
    if (!pending_commit_valid) {
        return 0;
    }
    return resolve_pending_commit();
}

static int commit_ring_state(const sd_ring_info_t *state, uint64_t data_id, bool is_clear)
{
    if (pending_commit_valid) {
        return -EBUSY;
    }

    int ret = write_journal_record(state, data_id);
    if (ret < 0) {
        return ret;
    }

    ret = sync_media();
    if (ret != 0) {
        LOG_ERR("metadata media sync failed: %d", ret);
        pending_commit_state = *state;
        pending_commit_data_id = data_id;
        pending_commit_clear = is_clear;
        pending_commit_valid = true;
        return -EIO;
    }

    publish_committed_state(state, data_id, is_clear);
    return 0;
}

static bool meta_slot_all_zero(const struct raw_meta_record *record)
{
    const uint8_t *bytes = (const uint8_t *) record;
    for (size_t i = 0; i < sizeof(*record); i++) {
        if (bytes[i] != 0U) {
            return false;
        }
    }
    return true;
}

static int load_ring_metadata(void)
{
    struct raw_meta_record best_record = {0};
    bool found = false;
    uint32_t best_slot = 0;
    uint64_t torn_gen_max = 0;
    uint64_t damaged_slots = 0;

    for (uint32_t slot = 0; slot < RAW_META_SECTORS; slot++) {
        int ret = disk_access_read(DISK_DRIVE_NAME, sector_buffer, slot, 1);
        if (ret != 0) {
            LOG_WRN("metadata read failed at slot %u: %d", slot, ret);
            damaged_slots |= BIT64(slot);
            continue;
        }

        struct raw_meta_record record;
        memcpy(&record, sector_buffer, sizeof(record));

        if (meta_record_valid(&record)) {
            if (!found || record.generation > best_record.generation) {
                best_record = record;
                best_slot = slot;
                found = true;
            }
            continue;
        }

        if (record.magic == RAW_META_MAGIC) {
            if (record.generation >= torn_gen_max) {
                torn_gen_max = record.generation;
            }
            continue;
        }

        if (!meta_slot_all_zero(&record)) {
            damaged_slots |= BIT64(slot);
        }
    }

    bool suspect = false;
    if (found) {
        uint32_t next_slot = (best_slot + 1U) % RAW_META_SECTORS;
        suspect = (torn_gen_max >= best_record.generation) || ((damaged_slots & BIT64(next_slot)) != 0U);
    }

    recovery_generation = found ? best_record.generation : 0;

    if (!found) {
        ring_state.read_seq = 0;
        ring_state.write_seq = 0;
        ring_state.dropped_packets = 0;
        ring_state.ring_id = 0;
        ring_data_id = 0;
        meta_generation = 0;
        meta_next_slot = 0;
    } else {
        ring_state.read_seq = best_record.read_seq;
        ring_state.write_seq = best_record.write_seq;
        ring_state.dropped_packets = best_record.dropped_packets;
        meta_generation = best_record.generation;
        meta_next_slot = (best_slot + 1U) % RAW_META_SECTORS;

        if (best_record.version == RAW_META_VERSION && !suspect) {
            ring_state.ring_id = best_record.ring_id;
            ring_data_id = best_record.data_id;
            return 0;
        }

        ring_data_id = (best_record.version == RAW_META_VERSION) ? best_record.data_id : 0U;
        ring_state.ring_id = 0;
    }

    int ret = ring_generate_id(&ring_state.ring_id);
    if (ret < 0) {
        return ret;
    }

    if (ring_data_id == 0U) {
        ret = ring_generate_id(&ring_data_id);
        if (ret < 0) {
            return ret;
        }
    }

    ret = write_journal_record(&ring_state, ring_data_id);
    if (ret < 0) {
        return ret;
    }

    ret = sync_media();
    if (ret != 0) {
        LOG_ERR("metadata media sync failed: %d", ret);
        return -EIO;
    }

    return 0;
}

static int load_batch_for_seq(uint64_t seq, uint8_t *buffer, struct raw_batch_header *header)
{
    if (!buffer || !header || data_batch_count == 0U) {
        return -EINVAL;
    }

    uint64_t base_seq = (seq / RAW_PACKETS_PER_BATCH) * RAW_PACKETS_PER_BATCH;
    if (cached_read_batch_valid && cached_read_batch_base_seq == base_seq) {
        if (buffer != batch_read_buffer) {
            memcpy(buffer, batch_read_buffer, sizeof(batch_read_buffer));
        }
        *header = cached_read_batch_header;
        return 0;
    }

    uint32_t sector = batch_sector_for_base_seq(base_seq);
    int ret = disk_access_read(DISK_DRIVE_NAME, buffer, sector, RAW_BATCH_SECTORS);
    if (ret != 0) {
        LOG_ERR("batch read failed at sector %u: %d", sector, ret);
        if (buffer == batch_read_buffer) {
            cached_read_batch_valid = false;
        }
        return -EIO;
    }

    memcpy(header, buffer, sizeof(*header));
    if (buffer == batch_read_buffer) {
        cached_read_batch_valid = false;
    }

    if (!batch_header_valid(header)) {
        LOG_ERR("invalid batch header for seq %llu", (unsigned long long) seq);
        return -EBADMSG;
    }

    if (header->start_seq != base_seq) {
        if (header->start_seq > base_seq && ring_state.capacity_packets != 0U &&
            ((header->start_seq - base_seq) % ring_state.capacity_packets) == 0U) {
            uint64_t overwritten_end_seq = base_seq + RAW_PACKETS_PER_BATCH;
            if (ring_state.read_seq < overwritten_end_seq) {
                sd_ring_info_t next = ring_state;
                next.dropped_packets += overwritten_end_seq - ring_state.read_seq;
                next.read_seq = overwritten_end_seq;
                (void) commit_ring_state(&next, ring_data_id, false);
            }

            LOG_WRN("stale read window for seq %llu: slot now holds batch %llu, advancing read_seq to %llu",
                    (unsigned long long) seq,
                    (unsigned long long) header->start_seq,
                    (unsigned long long) ring_state.read_seq);
            return -ERANGE;
        }

        LOG_ERR("batch start mismatch for seq %llu: hdr=%llu base=%llu",
                (unsigned long long) seq,
                (unsigned long long) header->start_seq,
                (unsigned long long) base_seq);
        return -EBADMSG;
    }

    if (buffer != batch_read_buffer) {
        memcpy(batch_read_buffer, buffer, sizeof(batch_read_buffer));
    }
    cached_read_batch_base_seq = base_seq;
    cached_read_batch_header = *header;
    cached_read_batch_valid = true;

    return 0;
}

static int restore_tail_batch(void)
{
    uint32_t partial_packets = (uint32_t) (ring_state.write_seq % RAW_PACKETS_PER_BATCH);
    if (partial_packets == 0U) {
        start_empty_batch(ring_state.write_seq);
        return 0;
    }

    uint64_t base_seq = ring_state.write_seq - partial_packets;
    struct raw_batch_header header;
    int ret = load_batch_for_seq(base_seq, current_batch, &header);
    if (ret < 0) {
        if (ret == -EIO) {
            return ret;
        }
        LOG_WRN("dropping incomplete tail batch after recovery error: %d", ret);
        sd_ring_info_t next = ring_state;
        next.write_seq = base_seq;
        if (next.read_seq > next.write_seq) {
            next.read_seq = next.write_seq;
        }
        int id_ret = ring_generate_id(&next.ring_id);
        if (id_ret < 0) {
            return id_ret;
        }
        int commit_ret = commit_ring_state(&next, ring_data_id, false);
        if (commit_ret < 0) {
            return commit_ret;
        }
        start_empty_batch(ring_state.write_seq);
        return 0;
    }

    if (header.packet_count != partial_packets) {
        LOG_WRN("tail packet count mismatch, truncating tail from %u to %u", partial_packets, header.packet_count);
        sd_ring_info_t next = ring_state;
        next.write_seq = header.start_seq + header.packet_count;
        if (next.read_seq > next.write_seq) {
            next.read_seq = next.write_seq;
        }
        int id_ret = ring_generate_id(&next.ring_id);
        if (id_ret < 0) {
            return id_ret;
        }
        int commit_ret = commit_ring_state(&next, ring_data_id, false);
        if (commit_ret < 0) {
            return commit_ret;
        }
    }

    current_batch_base_seq = header.start_seq;
    current_batch_packets = header.packet_count;
    current_batch_loaded = true;
    current_batch_dirty = false;
    return 0;
}

static int mount_continuity_check(void)
{
    if (ring_data_id == 0U || data_batch_count == 0U) {
        return 0;
    }

    invalidate_read_batch_cache();

    uint64_t salvage_end = ring_state.write_seq;
    bool found_newer = false;
    uint64_t base_seq = ring_state.write_seq - (ring_state.write_seq % RAW_PACKETS_PER_BATCH);
    uint64_t probe_limit = ring_state.write_seq + ring_state.capacity_packets;

    for (; base_seq < probe_limit; base_seq += RAW_PACKETS_PER_BATCH) {
        uint32_t sector = batch_sector_for_base_seq(base_seq);
        if (disk_access_read(DISK_DRIVE_NAME, batch_read_buffer, sector, RAW_BATCH_SECTORS) != 0) {
            LOG_ERR("continuity probe read failed at sector %u", sector);
            return -EIO;
        }

        struct raw_batch_header header;
        memcpy(&header, batch_read_buffer, sizeof(header));
        if (header.magic != RAW_BATCH_MAGIC || header.version != RAW_BATCH_VERSION ||
            batch_header_data_id(&header) != ring_data_id || header.start_seq != base_seq ||
            header.packet_count == 0U || header.packet_count > RAW_PACKETS_PER_BATCH) {
            break;
        }
        if (header.generation <= recovery_generation) {
            break;
        }

        LOG_WRN("batch at seq %llu is newer than metadata, salvaging %u records",
                (unsigned long long) base_seq,
                header.packet_count);
        found_newer = true;
        salvage_end = base_seq + header.packet_count;
        if (header.packet_count < RAW_PACKETS_PER_BATCH) {
            break;
        }
    }

    if (!found_newer) {
        return 0;
    }

    sd_ring_info_t next = ring_state;
    next.write_seq = salvage_end;
    if (next.write_seq - next.read_seq > next.capacity_packets) {
        uint64_t new_read = next.write_seq - next.capacity_packets;
        next.dropped_packets += new_read - next.read_seq;
        next.read_seq = new_read;
    }
    if (next.read_seq > next.write_seq) {
        next.read_seq = next.write_seq;
    }

    int ret = ring_generate_id(&next.ring_id);
    if (ret < 0) {
        return ret;
    }

    ret = commit_ring_state(&next, ring_data_id, false);
    if (ret < 0) {
        return ret;
    }

    invalidate_read_batch_cache();
    return restore_tail_batch();
}

static void live_mark_eval_committed(void)
{
    while (live_eval_count < current_batch_packets) {
        uint16_t idx = live_eval_count;
        omi_live_mark_note_record(
            &live_mark_state, current_batch_base_seq + idx, batch_live_session[idx], batch_live_index[idx]);
        live_eval_count++;
    }

    uint64_t mark_seq;
    uint16_t mark_index;
    uint32_t mark_session;
    if (omi_live_mark_eval(
            &live_mark_state, ring_state.write_seq, ring_state.read_seq, &mark_seq, &mark_index, &mark_session)) {
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
        (void) storage_queue_live_mark(ring_state.ring_id, mark_seq, mark_index, mark_session);
#endif
    }
}

static int flush_current_batch(bool sync_requested)
{
    int pending_ret = ensure_pending_resolved();
    if (pending_ret < 0) {
        return pending_ret;
    }

    /* SD is powered off (idle): keep the batch buffered in RAM, do not touch the
     * disk. It will be flushed after the next remount. */
    if (!is_mounted) {
        return 0;
    }

    if (!current_batch_loaded || !current_batch_dirty || current_batch_packets == 0U) {
        if (sync_requested) {
            int ret = sync_media();
            return (ret != 0) ? -EIO : 0;
        }
        return 0;
    }

    if (current_batch_base_seq > UINT64_MAX - current_batch_packets) {
        LOG_ERR("ring seq space exhausted, blocking writes");
        sd_write_blocked = true;
        return -EOVERFLOW;
    }

    struct raw_batch_header header = {
        .magic = RAW_BATCH_MAGIC,
        .version = RAW_BATCH_VERSION,
        .packet_count = current_batch_packets,
        .generation = meta_generation + 1U,
        .start_seq = current_batch_base_seq,
        .data_id_lo = (uint32_t) (ring_data_id & UINT32_MAX),
        .data_id_hi = (uint32_t) (ring_data_id >> 32),
    };
    memcpy(current_batch, &header, sizeof(header));

    uint32_t sector = batch_sector_for_base_seq(current_batch_base_seq);
    int ret = disk_access_write(DISK_DRIVE_NAME, current_batch, sector, RAW_BATCH_SECTORS);
    if (ret != 0) {
        writing_error_counter++;
        LOG_ERR("batch write failed at sector %u: %d", sector, ret);
        if (writing_error_counter > ERROR_THRESHOLD) {
            sd_write_blocked = true;
        }
        return -EIO;
    }

    ret = sync_media();
    if (ret != 0) {
        LOG_ERR("batch media sync failed at sector %u: %d", sector, ret);
        return -EIO;
    }

    uint64_t new_write_seq = current_batch_base_seq + current_batch_packets;
    sd_ring_info_t next = ring_state;

    if (next.write_seq <= current_batch_base_seq && current_batch_base_seq >= next.capacity_packets) {
        uint64_t overwritten_end_seq = current_batch_base_seq - next.capacity_packets + RAW_PACKETS_PER_BATCH;
        if (next.read_seq < overwritten_end_seq) {
            next.dropped_packets += overwritten_end_seq - next.read_seq;
            next.read_seq = overwritten_end_seq;
        }
    }

    if ((new_write_seq - next.read_seq) > next.capacity_packets) {
        uint64_t overflow = (new_write_seq - next.read_seq) - next.capacity_packets;
        next.read_seq += overflow;
        next.dropped_packets += overflow;
    }
    next.write_seq = new_write_seq;

    ret = commit_ring_state(&next, ring_data_id, false);
    if (ret < 0) {
        return ret;
    }

    current_batch_dirty = false;
    invalidate_read_batch_cache();
    writing_error_counter = 0;
    live_mark_eval_committed();

    if (current_batch_packets >= RAW_PACKETS_PER_BATCH) {
        start_empty_batch(ring_state.write_seq);
    }

    return 0;
}

static int clear_ring_internal(bool sync_requested)
{
    ARG_UNUSED(sync_requested);

    int pending_ret = ensure_pending_resolved();
    if (pending_ret < 0) {
        return pending_ret;
    }

    sd_ring_info_t next = ring_state;
    next.read_seq = 0;
    next.write_seq = 0;
    next.dropped_packets = 0;

    int ret = ring_generate_id(&next.ring_id);
    if (ret < 0) {
        return ret;
    }

    uint64_t new_data_id;
    ret = ring_generate_id(&new_data_id);
    if (ret < 0) {
        return ret;
    }

    return commit_ring_state(&next, new_data_id, true);
}

static int read_packets_internal(uint64_t start_seq,
                                 uint8_t *out_buf,
                                 uint32_t max_bytes,
                                 uint32_t *bytes_read,
                                 uint32_t *packets_read)
{
    if (!out_buf || !bytes_read || !packets_read) {
        return -EINVAL;
    }

    *bytes_read = 0;
    *packets_read = 0;

    if (!is_mounted) {
        return -ENODEV;
    }

    int pending_ret = ensure_pending_resolved();
    if (pending_ret < 0) {
        return pending_ret;
    }

    if (current_batch_dirty) {
        int flush_ret = flush_current_batch(false);
        if (flush_ret < 0) {
            return flush_ret;
        }
    }

    if (start_seq < ring_state.read_seq || start_seq > ring_state.write_seq) {
        return -ERANGE;
    }

    if (start_seq == ring_state.write_seq || max_bytes < RAW_AUDIO_PACKET_BYTES) {
        return 0;
    }

    uint32_t max_packets = max_bytes / RAW_AUDIO_PACKET_BYTES;
    uint64_t available_packets = ring_state.write_seq - start_seq;
    if ((uint64_t) max_packets > available_packets) {
        max_packets = (uint32_t) available_packets;
    }

    uint64_t seq = start_seq;
    uint32_t copied_packets = 0;
    uint64_t loaded_batch_base = UINT64_MAX;
    struct raw_batch_header loaded_header = {0};

    while (copied_packets < max_packets) {
        uint64_t batch_base = (seq / RAW_PACKETS_PER_BATCH) * RAW_PACKETS_PER_BATCH;
        if (batch_base != loaded_batch_base) {
            int ret = load_batch_for_seq(seq, batch_read_buffer, &loaded_header);
            if (ret < 0) {
                return ret;
            }
            loaded_batch_base = batch_base;
        }

        uint32_t packet_offset = (uint32_t) (seq - loaded_header.start_seq);
        if (packet_offset >= loaded_header.packet_count) {
            return -EIO;
        }

        uint32_t remaining_in_batch = loaded_header.packet_count - packet_offset;
        uint32_t copy_packets = MIN(max_packets - copied_packets, remaining_in_batch);
        size_t src_offset = RAW_BATCH_HEADER_BYTES + ((size_t) packet_offset * RAW_AUDIO_PACKET_BYTES);
        size_t copy_bytes = (size_t) copy_packets * RAW_AUDIO_PACKET_BYTES;
        memcpy(out_buf + (*bytes_read), batch_read_buffer + src_offset, copy_bytes);

        *bytes_read += (uint32_t) copy_bytes;
        copied_packets += copy_packets;
        seq += copy_packets;
    }

    *packets_read = copied_packets;
    return 0;
}

static int advance_read_seq_internal(uint64_t new_read_seq, uint64_t ring_id, bool check_id)
{
    if (pending_commit_valid) {
        int ret = resolve_pending_commit();
        if (ret < 0) {
            return ret;
        }
    }

    int ret = omi_advance_eval(
        ring_state.read_seq, ring_state.write_seq, ring_state.ring_id, ring_id, check_id, new_read_seq);
    if (ret < 0) {
        return ret;
    }

    if (new_read_seq <= ring_state.read_seq) {
        return 0;
    }

    sd_ring_info_t next = ring_state;
    next.read_seq = new_read_seq;
    return commit_ring_state(&next, ring_data_id, false);
}

static void process_write_data_req(const sd_req_t *req)
{
    if (sd_write_blocked || sd_write_paused || !req) {
        return;
    }

    if (req->u.write.len != MAX_WRITE_SIZE) {
        LOG_WRN("unexpected write size %u", (unsigned) req->u.write.len);
        return;
    }

    uint32_t timestamp = omi_record_timestamp(rtc_is_valid(), get_utc_time(), k_uptime_get());

    if (!current_batch_loaded) {
        start_empty_batch(ring_state.write_seq);
    }

    if (current_batch_packets >= RAW_PACKETS_PER_BATCH) {
        if (current_batch_dirty) {
            sd_set_io_low_power(false);
            (void) flush_current_batch(false);
            sd_set_io_low_power(true);
        }
        if (current_batch_packets >= RAW_PACKETS_PER_BATCH) {
            if (current_batch_dirty) {
                sd_write_drop_count++;
                LOG_ERR("dropping write: full batch still uncommitted");
                return;
            }
            start_empty_batch(ring_state.write_seq);
        }
    }

    size_t dst_offset = RAW_BATCH_HEADER_BYTES + ((size_t) current_batch_packets * RAW_AUDIO_PACKET_BYTES);
    sys_put_be32(timestamp, current_batch + dst_offset);
    memcpy(current_batch + dst_offset + RAW_AUDIO_TIMESTAMP_BYTES, req->u.write.buf, MAX_WRITE_SIZE);
    batch_live_session[current_batch_packets] = req->u.write.live_session;
    batch_live_index[current_batch_packets] = req->u.write.live_index;
    current_batch_packets++;
    if (!current_batch_dirty) {
        batch_dirty_since_ms = k_uptime_get();
    }
    current_batch_dirty = true;
    format_timestamp_name(timestamp, compat_current_name, sizeof(compat_current_name));

    bool queue_pressure_high = k_msgq_num_used_get(&sd_msgq) >= (SD_REQ_QUEUE_MSGS / 3);
    if (current_batch_packets >= RAW_PACKETS_PER_BATCH || queue_pressure_high) {
        sd_set_io_low_power(false);
        (void) flush_current_batch(false);
        sd_set_io_low_power(true);
    }
}

static int drain_pending_write_queue_for_shutdown(void)
{
    while (1) {
        if (pending_commit_valid) {
            int ret = resolve_pending_commit();
            if (ret < 0) {
                return ret;
            }
        }

        if (current_batch_packets >= RAW_PACKETS_PER_BATCH && current_batch_dirty) {
            int ret = flush_current_batch(false);
            if (ret < 0) {
                return ret;
            }
        }

        sd_req_t pending_req;
        if (k_msgq_get(&sd_msgq, &pending_req, K_NO_WAIT) != 0) {
            return 0;
        }

        if (pending_req.type == REQ_WRITE_DATA) {
            process_write_data_req(&pending_req);
        }
    }
}

static void sd_set_io_low_power(bool enable)
{
    if (!sd_enabled) {
        return;
    }

    if (enable) {
        if (!atomic_cas(&sd_io_low_power, 0, 1)) {
            return;
        }

        /* spi3 is shared with OTA external flash; only suspend the SD slot itself. */
        int ret_sd = 0;
        if (atomic_get(&sd_dev_pm_supported)) {
            ret_sd = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_SUSPEND);
            if (pm_action_is_unsupported(ret_sd)) {
                atomic_set(&sd_dev_pm_supported, 0);
            }
        }
        if (!pm_action_is_ok(ret_sd)) {
            LOG_WRN("SD suspend failed (sd=%d)", ret_sd);
        }
    } else {
        if (!atomic_cas(&sd_io_low_power, 1, 0)) {
            return;
        }

        int ret_sd = 0;
        if (atomic_get(&sd_dev_pm_supported)) {
            ret_sd = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_RESUME);
            if (pm_action_is_unsupported(ret_sd)) {
                atomic_set(&sd_dev_pm_supported, 0);
            }
        }
        if (!pm_action_is_ok(ret_sd)) {
            LOG_WRN("SD resume failed (sd=%d)", ret_sd);
        }
    }
}

static int sd_enable_power(bool enable)
{
    int ret;
    gpio_pin_configure_dt(&sd_en, GPIO_OUTPUT);

    if (enable) {
        ret = gpio_pin_set_dt(&sd_en, 1);
        if (atomic_get(&sd_dev_pm_supported)) {
            int ret_sd = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_RESUME);
            if (pm_action_is_unsupported(ret_sd)) {
                atomic_set(&sd_dev_pm_supported, 0);
            }
            if (!pm_action_is_ok(ret_sd)) {
                LOG_WRN("SD power-on resume failed (sd=%d)", ret_sd);
            }
        }
        atomic_set(&sd_io_low_power, 0);
        sd_enabled = true;
    } else {
        if (atomic_get(&sd_dev_pm_supported)) {
            int ret_sd = pm_device_action_run(sd_dev, PM_DEVICE_ACTION_SUSPEND);
            if (pm_action_is_unsupported(ret_sd)) {
                atomic_set(&sd_dev_pm_supported, 0);
            }
            if (!pm_action_is_ok(ret_sd)) {
                LOG_WRN("SD power-off suspend failed (sd=%d)", ret_sd);
            }
        }
        /* NOTE: the SD SPI chip-select (P1.11) is intentionally left managed by
         * the SPI driver here so the card can be re-initialised after a power
         * cycle. Full shutdown (app_sd_off) disconnects it separately to kill the
         * last bit of leakage since no remount follows. */
        ret = gpio_pin_set_dt(&sd_en, 0);
        atomic_set(&sd_io_low_power, 0);
        sd_enabled = false;
    }

    return ret;
}

static int sd_mount(void)
{
    if (is_mounted) {
        return 0;
    }

    int ret = -EIO;
    uint32_t sector_size = 0;

    for (int attempt = 1; attempt <= 5; attempt++) {
        ret = sd_enable_power(true);
        if (ret < 0) {
            LOG_ERR("SD power on failed: %d", ret);
            return ret;
        }

        k_msleep(50 * attempt);
        ret = disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_INIT, NULL);
        if (ret == 0) {
            break;
        }

        LOG_WRN("SD CTRL_INIT attempt %d/5 failed: %d", attempt, ret);
        (void) disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_DEINIT, NULL);
        sd_enable_power(false);
        k_msleep(50);
    }

    if (ret != 0) {
        LOG_ERR("Disk CTRL_INIT failed after retries: %d", ret);
        return ret;
    }

    (void) disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_GET_SECTOR_COUNT, &disk_sector_count);
    (void) disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_GET_SECTOR_SIZE, &sector_size);

    if (sector_size != DISK_SECTOR_SIZE || disk_sector_count <= RAW_META_SECTORS) {
        LOG_ERR("unexpected SD layout: sectors=%u size=%u", disk_sector_count, sector_size);
        sd_enable_power(false);
        return -EINVAL;
    }

    data_batch_count = (disk_sector_count - RAW_META_SECTORS) / RAW_BATCH_SECTORS;
    if (data_batch_count == 0U) {
        LOG_ERR("not enough sectors for raw ring layout");
        sd_enable_power(false);
        return -ENOSPC;
    }

    ring_state.capacity_packets = data_batch_count * RAW_PACKETS_PER_BATCH;

    ret = load_ring_metadata();
    if (ret < 0) {
        LOG_ERR("failed to load raw ring metadata: %d", ret);
        sd_enable_power(false);
        return ret;
    }

    ret = restore_tail_batch();
    if (ret < 0) {
        LOG_ERR("tail recovery could not establish ring continuity: %d", ret);
        sd_enable_power(false);
        return ret;
    }

    ret = mount_continuity_check();
    if (ret < 0) {
        LOG_ERR("mount continuity check failed: %d", ret);
        sd_enable_power(false);
        return ret;
    }

    is_mounted = true;

    LOG_INF("Raw SD ring mounted: sectors=%u, batches=%u, capacity=%u packets",
            disk_sector_count,
            data_batch_count,
            ring_state.capacity_packets);
    return 0;
}

static int sd_unmount(void)
{
    if (current_batch_dirty) {
        int ret = flush_current_batch(true);
        if (ret < 0) {
            LOG_ERR("unmount aborted: dirty batch flush failed (%d)", ret);
            return ret;
        }
    } else {
        int ret = sync_media();
        if (ret != 0) {
            LOG_ERR("unmount aborted: media sync failed (%d)", ret);
            return -EIO;
        }
    }

    if (is_mounted) {
        (void) disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_DEINIT, NULL);
        is_mounted = false;
    }

    sd_enable_power(false);
    LOG_INF("Raw SD ring unmounted");
    return 0;
}

static int get_packet_name_for_seq(uint64_t seq, char *buf, size_t buf_size)
{
    if (!buf || buf_size == 0U) {
        return -EINVAL;
    }

    uint8_t packet[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes_read = 0;
    uint32_t packets_read = 0;
    int ret = sd_ring_read(seq, packet, sizeof(packet), &bytes_read, &packets_read);
    if (ret < 0 || packets_read == 0U) {
        return (ret < 0) ? ret : -ENOENT;
    }

    format_timestamp_name(sys_get_be32(packet), buf, buf_size);
    return 0;
}

void sd_worker_thread(void)
{
    sd_req_t req;

    int res = sd_mount();
    if (res != 0) {
        LOG_ERR("[SD_WORK] mount failed: %d", res);
        sd_write_blocked = true;
        return;
    }

    atomic_set(&sd_boot_ready, 1);
    LOG_INF("[SD_BOOT] raw ring ready (used=%llu bytes)", (unsigned long long) ring_used_bytes());
    sd_set_io_low_power(true);

    while (1) {
        if (atomic_cas(&pending_flush_on_ble_connect, 1, 0)) {
            req.type = REQ_FLUSH;
            req.u.status.resp = NULL;
            goto handle_req;
        }

        if (k_msgq_get(&sd_prio_msgq, &req, K_NO_WAIT) == 0) {
            goto handle_req;
        }

        if (pending_commit_valid) {
            sd_set_io_low_power(false);
            (void) resolve_pending_commit();
            sd_set_io_low_power(true);
        }

        if (current_batch_dirty && (k_uptime_get() - batch_dirty_since_ms) >= RAW_FLUSH_INTERVAL_MS) {
            sd_set_io_low_power(false);
            (void) flush_current_batch(false);
            sd_set_io_low_power(true);
        }

        bool backlog_full = current_batch_packets >= RAW_PACKETS_PER_BATCH && current_batch_dirty;
        if (backlog_full) {
            sd_set_io_low_power(false);
            (void) flush_current_batch(false);
            sd_set_io_low_power(true);
            backlog_full = current_batch_packets >= RAW_PACKETS_PER_BATCH && current_batch_dirty;
        }

        k_timeout_t write_wait = ble_connected ? K_MSEC(50) : K_MSEC(250);
        if (pending_commit_valid || backlog_full) {
            k_msleep(ble_connected ? 50 : 250);
            continue;
        }

        if (k_msgq_get(&sd_msgq, &req, write_wait) != 0) {
            continue;
        }

    handle_req:
        if (req.type != REQ_WRITE_DATA) {
            sd_set_io_low_power(false);
        }

        switch (req.type) {
        case REQ_WRITE_DATA:
            /* If the SD was powered off (mic just woke), a write can be dequeued
             * before the POWER_ON prio request is seen. Mount first so buffered
             * audio lands on a valid ring, then process the write in order. */
            if (!is_mounted) {
                /* CS was parked low on power-off; restore physical high before mount.
                 * Mount directly rather than draining the prio queue looking for the
                 * POWER_ON (that would discard unrelated sync/read prio requests).
                 * The pending POWER_ON stays queued and is a no-op once mounted. */
                gpio_pin_set_raw(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 11, 1);
                if (sd_mount() != 0) {
                    sd_write_drop_count++;
                    LOG_ERR("dropping write: SD mount failed");
                    break;
                }
            }
            process_write_data_req(&req);
            for (int i = 0; i < WRITE_DRAIN_BURST; i++) {
                if (k_msgq_num_used_get(&sd_prio_msgq) > 0) {
                    break;
                }

                if (pending_commit_valid) {
                    break;
                }
                if (current_batch_packets >= RAW_PACKETS_PER_BATCH && current_batch_dirty) {
                    break;
                }

                sd_req_t next_req;
                if (k_msgq_get(&sd_msgq, &next_req, K_NO_WAIT) != 0) {
                    break;
                }

                if (next_req.type == REQ_WRITE_DATA) {
                    process_write_data_req(&next_req);
                }
            }
            break;

        case REQ_GET_RING_INFO:
            if (pending_commit_valid && resolve_pending_commit() < 0) {
                if (req.u.info.resp) {
                    req.u.info.resp->res = -EIO;
                    k_sem_give(&req.u.info.resp->sem);
                    release_resp_busy(req.u.info.resp->busy_flag);
                }
                break;
            }
            if (current_batch_dirty) {
                int flush_ret = flush_current_batch(false);
                if (req.u.info.resp && flush_ret < 0) {
                    req.u.info.resp->res = flush_ret;
                    k_sem_give(&req.u.info.resp->sem);
                    release_resp_busy(req.u.info.resp->busy_flag);
                    break;
                }
            }
            if (req.u.info.resp) {
                req.u.info.resp->info = ring_state;
                req.u.info.resp->res = 0;
                k_sem_give(&req.u.info.resp->sem);
                release_resp_busy(req.u.info.resp->busy_flag);
            }
            break;

        case REQ_READ_PACKETS:
            if (req.u.read.resp) {
                req.u.read.resp->res = read_packets_internal(req.u.read.start_seq,
                                                             req.u.read.out_buf,
                                                             req.u.read.max_bytes,
                                                             &req.u.read.resp->bytes_read,
                                                             &req.u.read.resp->packets_read);
                k_sem_give(&req.u.read.resp->sem);
                release_resp_busy(req.u.read.resp->busy_flag);
            }
            break;

        case REQ_ADVANCE_READ: {
            /* Perform the advance regardless; a NULL resp is a fire-and-forget
             * request that must not block the worker. */
            int adv_res =
                advance_read_seq_internal(req.u.advance.new_read_seq, req.u.advance.ring_id, req.u.advance.check_id);
            if (req.u.advance.resp) {
                req.u.advance.resp->res = adv_res;
                k_sem_give(&req.u.advance.resp->sem);
                release_resp_busy(req.u.advance.resp->busy_flag);
            }
            break;
        }

        case REQ_CLEAR_RING:
            if (req.u.status.resp) {
                req.u.status.resp->res = clear_ring_internal(false);
                k_sem_give(&req.u.status.resp->sem);
                release_resp_busy(req.u.status.resp->busy_flag);
            }
            break;

        case REQ_FLUSH:
            if (req.u.status.resp) {
                req.u.status.resp->res = flush_current_batch(true);
                k_sem_give(&req.u.status.resp->sem);
                release_resp_busy(req.u.status.resp->busy_flag);
            } else {
                (void) flush_current_batch(true);
            }
            break;

        case REQ_UNMOUNT: {
            int drain_res = drain_pending_write_queue_for_shutdown();
            int unmount_res = (drain_res < 0) ? drain_res : sd_unmount();
            res = (drain_res < 0) ? drain_res : unmount_res;
            if (req.u.status.resp) {
                req.u.status.resp->res = res;
                k_sem_give(&req.u.status.resp->sem);
                release_resp_busy(req.u.status.resp->busy_flag);
            }
            break;
        }

        case REQ_POWER_OFF:
            /* Idle (mic asleep): flush, unmount and cut SD power to save current.
             * Drain buffered writes first (like the shutdown path) so audio queued
             * just before idle is not lost when we unmount. */
            if (is_mounted) {
                if (drain_pending_write_queue_for_shutdown() != 0) {
                    LOG_ERR("SD power-off aborted: write drain failed");
                    break;
                }
                if (sd_unmount() != 0) {
                    LOG_ERR("SD power-off aborted: unmount failed");
                    break;
                }
                /* Park the SD chip-select at physical 0 V. The SPI driver otherwise
                 * idles it HIGH, which forward-biases the unpowered card's input
                 * clamp and leaks current. Use *_raw so the driver's active-low
                 * inversion does not flip the level. Keep it an output owned by the
                 * driver (do NOT disconnect) so the card still re-inits on wake.
                 * SCK/MOSI/MISO are shared with the OTA flash on spi3, not parked. */
                gpio_pin_set_raw(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 11, 0);
                LOG_INF("SD powered off (idle, CS parked low)");
            }
            break;

        case REQ_POWER_ON:
            /* Mic woke: power on + remount. Handled via the prio queue so it runs
             * before any buffered write is dequeued from sd_msgq. */
            if (!is_mounted) {
                /* CS back to inactive (physical high) before powering the card, per
                 * SD SPI power-up sequencing. */
                gpio_pin_set_raw(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 11, 1);
                int mret = sd_mount();
                if (mret == 0) {
                    LOG_INF("SD powered on + remounted");
                } else {
                    LOG_ERR("SD remount failed: %d", mret);
                }
            }
            break;
        }

        if (req.type != REQ_WRITE_DATA) {
            sd_set_io_low_power(true);
        }
    }
}

int app_sd_init(void)
{
    sd_shutdown_in_progress = false;
    sd_write_blocked = false;
    sd_write_paused = false;
    if (!sd_worker_tid) {
        sd_worker_tid = k_thread_create(&sd_worker_thread_data,
                                        sd_worker_stack,
                                        SD_WORKER_STACK_SIZE,
                                        (k_thread_entry_t) sd_worker_thread,
                                        NULL,
                                        NULL,
                                        NULL,
                                        SD_WORKER_PRIORITY,
                                        0,
                                        K_NO_WAIT);
        k_thread_name_set(sd_worker_tid, "sd_worker");
    }
    return 0;
}

int app_sd_off(void)
{
    sd_shutdown_in_progress = true;
    bool unmount_completed = false;

    if (is_mounted && sd_worker_tid) {
        struct status_resp resp;
        k_sem_init(&resp.sem, 0, 1);
        resp.busy_flag = NULL;
        resp.res = 0;

        sd_req_t req = {0};
        req.type = REQ_UNMOUNT;
        req.u.status.resp = &resp;

        int qret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(2000));
        if (qret == 0) {
            if (k_sem_take(&resp.sem, K_MSEC(45000)) == 0 && resp.res >= 0) {
                unmount_completed = true;
            } else {
                LOG_ERR("Timeout waiting for raw ring unmount");
            }
        } else {
            LOG_ERR("Failed to queue raw ring unmount request: %d", qret);
        }
    }

    if (unmount_completed || !is_mounted) {
        if (sd_enabled) {
            sd_enable_power(false);
        }
        sd_enabled = false;

        /* Full shutdown: no remount follows, so disconnect the SD chip-select
         * (P1.11) to remove the last leakage path into the unpowered card. */
        gpio_pin_configure(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 11, GPIO_DISCONNECTED);

        const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi3));
        if (device_is_ready(spi_dev)) {
            int ret = pm_device_action_run(spi_dev, PM_DEVICE_ACTION_SUSPEND);
            if (ret < 0 && ret != -EALREADY && ret != -ENOSYS && ret != -ENOTSUP) {
                LOG_WRN("SPI3 shutdown suspend failed: %d", ret);
            }
        }
    }

    return 0;
}

bool is_sd_on(void)
{
    return sd_enabled;
}

bool sd_is_ready(void)
{
    /* Powered AND actually mounted -> ring reads will succeed. During a
     * power-on the card is enabled but not yet mounted (~remount latency). */
    return sd_enabled && is_mounted;
}

void sd_write_pause(bool pause)
{
    sd_write_paused = pause;
}

void sd_request_power(bool on)
{
    sd_req_t req = {0};
    req.type = on ? REQ_POWER_ON : REQ_POWER_OFF;

    /* Queue with a timeout and check the result (like the other prio-queue
     * callers). A silently dropped REQ_POWER_ON would leave sd_enabled=true with
     * no remount -> subsequent writes lost. */
    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret != 0) {
        LOG_ERR("sd_request_power(%s) failed to queue: %d", on ? "on" : "off", ret);
        return;
    }

    if (on) {
        /* Only after the POWER_ON is queued: mark SD available so the audio
         * pusher keeps writing; the writes buffer in sd_msgq until the remount
         * (prio request) completes. */
        sd_enabled = true;
    }
}

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE

void sd_notify_time_synced(uint32_t utc_time)
{
    ARG_UNUSED(utc_time);
}

void sd_notify_ble_state(bool connected)
{
    if (connected && !ble_connected) {
        sd_req_t req = {0};
        req.type = REQ_FLUSH;
        req.u.status.resp = NULL;
        int ret = k_msgq_put(&sd_prio_msgq, &req, K_NO_WAIT);
        if (ret != 0) {
            atomic_set(&pending_flush_on_ble_connect, 1);
        }
    }

    ble_connected = connected;
}

uint32_t write_to_file(uint8_t *data, uint32_t length)
{
    static int64_t last_write_err_log_ms;
    static int64_t last_shutdown_drop_log_ms;
    static int64_t last_not_ready_log_ms;

    if (!atomic_get(&sd_boot_ready)) {
        int64_t now = k_uptime_get();
        if (now - last_not_ready_log_ms > 5000) {
            LOG_WRN("write_to_file dropped: SD not ready");
            last_not_ready_log_ms = now;
        }
        return 0;
    }

    if (sd_shutdown_in_progress || sd_write_paused) {
        int64_t now = k_uptime_get();
        if (now - last_shutdown_drop_log_ms > 1000) {
            LOG_WRN("write_to_file dropped: SD paused/shutdown");
            last_shutdown_drop_log_ms = now;
        }
        return 0;
    }

    if (sd_write_blocked) {
        int64_t now = k_uptime_get();
        if (now - last_write_blocked_log_ms > 1000) {
            LOG_ERR("write_to_file blocked");
            last_write_blocked_log_ms = now;
        }
        return 0;
    }

    if (!data || length != MAX_WRITE_SIZE) {
        return 0;
    }

    sd_req_t req = {0};
    req.type = REQ_WRITE_DATA;
    memcpy(req.u.write.buf, data, length);
    req.u.write.len = length;
    req.u.write.live_session = 0;
    req.u.write.live_index = 0;

    int ret = k_msgq_put(&sd_msgq, &req, K_NO_WAIT);
    if (ret != 0) {
        ret = k_msgq_put(&sd_msgq, &req, ble_connected ? K_MSEC(1) : K_MSEC(5));
    }

    if (ret != 0) {
        write_drop_packets++;
        write_drop_bytes += length;
        int64_t now = k_uptime_get();
        if (now - last_write_err_log_ms > 2000) {
            LOG_WRN("Write queue full, dropping audio data (%d), dropped=%u pkts (%u bytes)",
                    ret,
                    write_drop_packets,
                    write_drop_bytes);
            last_write_err_log_ms = now;
        }
        return 0;
    }

    return length;
}

int sd_ring_get_info(sd_ring_info_t *info)
{
    if (!info) {
        return -EINVAL;
    }

    static struct info_resp resp;
    static atomic_t info_in_flight = ATOMIC_INIT(0);

    if (!atomic_cas(&info_in_flight, 0, 1)) {
        return -EBUSY;
    }

    k_sem_init(&resp.sem, 0, 1);
    resp.busy_flag = &info_in_flight;

    sd_req_t req = {0};
    req.type = REQ_GET_RING_INFO;
    req.u.info.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret != 0) {
        resp.busy_flag = NULL;
        atomic_clear(&info_in_flight);
        return ret;
    }

    ret = wait_for_sd_worker_response(&resp.sem, 5000, "sd_ring_get_info");
    if (ret < 0) {
        return ret;
    }

    *info = resp.info;
    return resp.res;
}

int sd_ring_read(uint64_t start_seq, uint8_t *buf, uint32_t max_bytes, uint32_t *bytes_read, uint32_t *packets_read)
{
    if (!buf || !bytes_read || !packets_read) {
        return -EINVAL;
    }

    static struct read_resp resp;
    static atomic_t read_in_flight = ATOMIC_INIT(0);

    if (!atomic_cas(&read_in_flight, 0, 1)) {
        return -EBUSY;
    }

    k_sem_init(&resp.sem, 0, 1);
    resp.busy_flag = &read_in_flight;
    resp.bytes_read = 0;
    resp.packets_read = 0;

    sd_req_t req = {0};
    req.type = REQ_READ_PACKETS;
    req.u.read.start_seq = start_seq;
    req.u.read.max_bytes = max_bytes;
    req.u.read.out_buf = buf;
    req.u.read.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret != 0) {
        resp.busy_flag = NULL;
        atomic_clear(&read_in_flight);
        return ret;
    }

    ret = wait_for_sd_worker_response(&resp.sem, 15000, "sd_ring_read");
    if (ret < 0) {
        return ret;
    }

    *bytes_read = resp.bytes_read;
    *packets_read = resp.packets_read;
    return resp.res;
}

static int sd_ring_advance_common(uint64_t ring_id, bool check_id, uint64_t new_read_seq, const char *op_name)
{
    static struct status_resp resp;
    static atomic_t advance_in_flight = ATOMIC_INIT(0);

    if (!atomic_cas(&advance_in_flight, 0, 1)) {
        return -EBUSY;
    }

    k_sem_init(&resp.sem, 0, 1);
    resp.busy_flag = &advance_in_flight;

    sd_req_t req = {0};
    req.type = REQ_ADVANCE_READ;
    req.u.advance.new_read_seq = new_read_seq;
    req.u.advance.ring_id = ring_id;
    req.u.advance.check_id = check_id;
    req.u.advance.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret != 0) {
        resp.busy_flag = NULL;
        atomic_clear(&advance_in_flight);
        return ret;
    }

    ret = wait_for_sd_worker_response(&resp.sem, 5000, op_name);
    if (ret < 0) {
        return ret;
    }

    return resp.res;
}

int sd_ring_advance(uint64_t new_read_seq)
{
    return sd_ring_advance_common(0, false, new_read_seq, "sd_ring_advance");
}

int sd_ring_advance_id(uint64_t ring_id, uint64_t new_read_seq)
{
    return sd_ring_advance_common(ring_id, true, new_read_seq, "sd_ring_advance_id");
}

uint32_t sd_ring_write_record(const uint8_t *data, uint32_t length, uint32_t live_session, uint16_t live_index)
{
    if (!data || length != MAX_WRITE_SIZE || !atomic_get(&sd_boot_ready) || sd_shutdown_in_progress ||
        sd_write_paused || sd_write_blocked) {
        return 0;
    }

    sd_req_t req = {0};
    req.type = REQ_WRITE_DATA;
    memcpy(req.u.write.buf, data, length);
    req.u.write.len = length;
    req.u.write.live_session = live_session;
    req.u.write.live_index = live_index;

    if (k_msgq_put(&sd_msgq, &req, K_NO_WAIT) != 0) {
        return 0;
    }

    return length;
}

int sd_ring_clear(void)
{
    static struct status_resp resp;
    static atomic_t clear_in_flight = ATOMIC_INIT(0);

    if (!atomic_cas(&clear_in_flight, 0, 1)) {
        return -EBUSY;
    }

    k_sem_init(&resp.sem, 0, 1);
    resp.busy_flag = &clear_in_flight;

    sd_req_t req = {0};
    req.type = REQ_CLEAR_RING;
    req.u.status.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret != 0) {
        resp.busy_flag = NULL;
        atomic_clear(&clear_in_flight);
        return ret;
    }

    ret = wait_for_sd_worker_response(&resp.sem, 15000, "sd_ring_clear");
    if (ret < 0) {
        return ret;
    }

    return resp.res;
}

int sd_flush_current_file(void)
{
    static struct status_resp resp;
    static atomic_t flush_in_flight = ATOMIC_INIT(0);

    if (!atomic_cas(&flush_in_flight, 0, 1)) {
        return -EBUSY;
    }

    k_sem_init(&resp.sem, 0, 1);
    resp.busy_flag = &flush_in_flight;

    sd_req_t req = {0};
    req.type = REQ_FLUSH;
    req.u.status.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret != 0) {
        resp.busy_flag = NULL;
        atomic_clear(&flush_in_flight);
        return ret;
    }

    ret = wait_for_sd_worker_response(&resp.sem, 30000, "sd_flush_current_file");
    if (ret < 0) {
        return ret;
    }

    return resp.res;
}

uint32_t get_file_size(void)
{
    uint64_t used = ring_used_bytes();
    return (used > UINT32_MAX) ? UINT32_MAX : (uint32_t) used;
}

int get_current_filename(char *buf, size_t buf_size)
{
    if (!buf || buf_size < MAX_FILENAME_LEN) {
        return -EINVAL;
    }

    strncpy(buf, compat_current_name, buf_size - 1);
    buf[buf_size - 1] = '\0';
    return 0;
}

int clear_audio_directory(void)
{
    return sd_ring_clear();
}

int save_offset(const char *filename, uint32_t offset)
{
    if (filename) {
        strncpy(compat_saved_name, filename, sizeof(compat_saved_name) - 1);
        compat_saved_name[sizeof(compat_saved_name) - 1] = '\0';
    } else {
        compat_saved_name[0] = '\0';
    }
    compat_saved_offset = offset;
    return 0;
}

int get_offset(char *filename, uint32_t *offset)
{
    if (!filename || !offset) {
        return -EINVAL;
    }

    strncpy(filename, compat_saved_name, MAX_FILENAME_LEN - 1);
    filename[MAX_FILENAME_LEN - 1] = '\0';
    *offset = compat_saved_offset;
    return 0;
}

int create_new_audio_file(void)
{
    return sd_flush_current_file();
}

int get_audio_file_stats(uint32_t *file_count, uint64_t *total_size)
{
    if (!file_count || !total_size) {
        return -EINVAL;
    }

    sd_ring_info_t info;
    int ret = sd_ring_get_info(&info);
    if (ret < 0) {
        return ret;
    }

    *file_count = (info.write_seq > info.read_seq) ? 1U : 0U;
    *total_size = (info.write_seq - info.read_seq) * RAW_AUDIO_PACKET_BYTES;
    return 0;
}

int get_audio_file_list(char filenames[][MAX_FILENAME_LEN], int max_files, int *count)
{
    return get_audio_file_list_with_sizes(filenames, NULL, max_files, count);
}

int get_audio_file_list_with_sizes(char filenames[][MAX_FILENAME_LEN], uint32_t *sizes, int max_files, int *count)
{
    if (!filenames || !count || max_files <= 0) {
        return -EINVAL;
    }

    for (int attempt = 0; attempt < 3; attempt++) {
        sd_ring_info_t info;
        int ret = sd_ring_get_info(&info);
        if (ret < 0) {
            return ret;
        }

        if (info.read_seq == info.write_seq) {
            *count = 0;
            return 0;
        }

        ret = get_packet_name_for_seq(info.read_seq, filenames[0], MAX_FILENAME_LEN);
        if (ret == -ERANGE) {
            continue;
        }
        if (ret < 0) {
            return ret;
        }

        if (sizes) {
            uint64_t used = (info.write_seq - info.read_seq) * RAW_AUDIO_PACKET_BYTES;
            sizes[0] = (used > UINT32_MAX) ? UINT32_MAX : (uint32_t) used;
        }

        *count = 1;
        return 0;
    }

    return -EAGAIN;
}

int delete_audio_file(const char *filename)
{
    ARG_UNUSED(filename);
    return sd_ring_clear();
}

int read_audio_data(const char *filename, uint8_t *buf, int amount, int offset)
{
    ARG_UNUSED(filename);

    if (!buf || amount <= 0 || offset < 0) {
        return -EINVAL;
    }

    int flush_ret = sd_flush_current_file();
    if (flush_ret < 0) {
        return flush_ret;
    }

    sd_ring_info_t info;
    int ret = sd_ring_get_info(&info);
    if (ret < 0) {
        return ret;
    }

    uint64_t stream_bytes = (info.write_seq - info.read_seq) * RAW_AUDIO_PACKET_BYTES;
    if ((uint64_t) offset >= stream_bytes) {
        return 0;
    }

    static uint8_t compat_buffer[RAW_AUDIO_PACKET_BYTES * 8U];
    uint64_t seq = info.read_seq + ((uint32_t) offset / RAW_AUDIO_PACKET_BYTES);
    uint32_t inner_offset = (uint32_t) offset % RAW_AUDIO_PACKET_BYTES;
    int total_read = 0;

    while (total_read < amount && seq < info.write_seq) {
        uint32_t bytes_read = 0;
        uint32_t packets_read = 0;
        ret = sd_ring_read(seq, compat_buffer, sizeof(compat_buffer), &bytes_read, &packets_read);
        if (ret < 0) {
            return (total_read > 0) ? total_read : ret;
        }
        if (bytes_read <= inner_offset || packets_read == 0U) {
            break;
        }

        uint32_t available = bytes_read - inner_offset;
        uint32_t copy_bytes = MIN((uint32_t) (amount - total_read), available);
        memcpy(buf + total_read, compat_buffer + inner_offset, copy_bytes);
        total_read += (int) copy_bytes;
        seq += packets_read;
        inner_offset = 0;
    }

    return total_read;
}

#endif