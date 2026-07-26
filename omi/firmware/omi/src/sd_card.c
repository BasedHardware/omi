#include "lib/core/sd_card.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/util.h>

#include "lib/core/ring_transfer_integrity.h"
#include "lib/core/sd_ring_durability.h"
#include "lib/core/sd_ring_recovery.h"
#include "lib/core/sd_write_recovery.h"
#include "lib/core/settings.h"
#ifdef CONFIG_OMI_ENABLE_MONITOR
#include "lib/core/monitor.h"
#endif
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
#define RAW_META_LAYOUT_VERSION_LEGACY 1U
#define RAW_META_LAYOUT_VERSION_CRC 2U
#define RAW_BATCH_LAYOUT_VERSION_LEGACY 1U
#define RAW_BATCH_LAYOUT_VERSION_CRC 2U

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
    uint32_t metadata_crc32;
} __packed;

struct raw_batch_header {
    uint32_t magic;
    uint16_t version;
    uint16_t packet_count;
    uint64_t generation;
    uint64_t start_seq;
    uint32_t payload_crc32;
    uint32_t reserved1;
};

BUILD_ASSERT(sizeof(struct raw_meta_record) == 44U, "raw metadata record layout changed");
BUILD_ASSERT(sizeof(struct raw_batch_header) == RAW_BATCH_HEADER_BYTES, "raw batch header layout changed");

typedef enum {
    RING_METADATA_RUNTIME_MUTATION,
    RING_METADATA_QUARANTINE_OWNER,
    RING_METADATA_QUARANTINE_RECOVERY,
} ring_metadata_authority_t;

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
            uint32_t timestamp;
        } write;
        struct {
            uint64_t start_seq;
            uint32_t max_bytes;
            uint8_t *out_buf;
            struct read_resp *resp;
        } read;
        struct {
            uint64_t new_read_seq;
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
static atomic_t pending_power_on;
static atomic_t pending_idle_power_off;
static atomic_t desired_sd_power_on = ATOMIC_INIT(1);
static atomic_t storage_health = ATOMIC_INIT(SD_STORAGE_HEALTHY);
#define SD_POWER_ON_RETRY_MS 250U
#define SD_POWER_OFF_RETRY_MS 1000U
static int64_t power_on_retry_deadline_ms;
static int64_t idle_power_off_retry_deadline_ms;

static bool is_mounted;
static bool sd_enabled;
static bool sd_shutdown_in_progress;
static bool sd_write_blocked;
static bool ble_connected;

static uint32_t disk_sector_count;
static uint32_t data_batch_count;
static uint32_t meta_next_slot;
static uint64_t meta_generation;
static sd_ring_info_t ring_state;
static sd_ring_durability_t ring_durability;

static uint8_t current_batch[RAW_BATCH_BYTES];
static uint8_t batch_read_buffer[RAW_BATCH_BYTES];
static uint8_t sector_buffer[DISK_SECTOR_SIZE];
static uint16_t current_batch_packets;
static uint16_t current_batch_durable_packets;
static bool current_batch_crc_protected;
static uint64_t current_batch_base_seq;
static uint64_t cached_read_batch_base_seq = UINT64_MAX;
static struct raw_batch_header cached_read_batch_header;
static bool current_batch_loaded;
static bool current_batch_dirty;
static bool cached_read_batch_valid;
static int64_t next_batch_flush_attempt_ms;

static uint32_t write_rejected_records;
static uint32_t terminal_at_risk_records;
static int64_t last_write_blocked_log_ms;
static int64_t last_terminal_record_log_ms;
static sd_req_t retained_write_req;
static bool retained_write_pending;
static uint32_t retained_write_retry_delay_ms;
static int64_t retained_write_retry_deadline_ms;
static sd_write_recovery_policy_t write_recovery_policy;
static sd_write_recovery_action_t write_recovery_action;

static char compat_current_name[MAX_FILENAME_LEN];
static char compat_saved_name[MAX_FILENAME_LEN];
static uint32_t compat_saved_offset;

static void sd_worker_thread(void);
static void sd_set_io_low_power(bool enable);
static int flush_current_batch(bool sync_media);
static int sd_mount_internal(bool restore_ring_state);
static int sd_mount(void);
static int recover_sd_media_preserving_ram(void);

static int mount_for_pending_write(void)
{
    return current_batch_dirty ? sd_mount_internal(false) : sd_mount();
}

static void record_terminal_at_risk_records(uint32_t count, const char *reason)
{
    if (count == 0U) {
        return;
    }

    terminal_at_risk_records += count;
#ifdef CONFIG_OMI_ENABLE_MONITOR
    for (uint32_t i = 0; i < count; i++) {
        monitor_inc_storage_write_failed();
    }
#endif

    int64_t now = k_uptime_get();
    if (now >= last_terminal_record_log_ms) {
        LOG_ERR("SD terminal: %u accepted record(s) at risk (%s), total=%u", count, reason, terminal_at_risk_records);
        last_terminal_record_log_ms = now + 2000;
    }
}

static void enter_sd_write_terminal(int error)
{
    if (atomic_get(&storage_health) == SD_STORAGE_TERMINAL) {
        return;
    }

    atomic_set(&storage_health, SD_STORAGE_TERMINAL);
    sd_write_blocked = true;
    write_recovery_action = SD_WRITE_RECOVERY_ACTION_TERMINAL;
    sd_ring_durability_enter_terminal(&ring_durability);
    uint64_t unsafe_packets = sd_ring_durability_unsafe_packets(&ring_durability);
    record_terminal_at_risk_records((uint32_t) MIN(unsafe_packets, UINT32_MAX), "unsafe durable tail");
    uint32_t dirty_records = current_batch_packets > current_batch_durable_packets
                                 ? current_batch_packets - current_batch_durable_packets
                                 : 0U;
    record_terminal_at_risk_records(dirty_records, "dirty batch");
    LOG_ERR("SD write recovery exhausted after %u remounts: terminal error=%d; offline frames will be explicitly "
            "rejected while live BLE remains available",
            write_recovery_policy.remounts,
            error);
}

static void note_sd_write_failure(int error)
{
    write_recovery_action = sd_write_recovery_on_failure(&write_recovery_policy);
    if (write_recovery_action == SD_WRITE_RECOVERY_ACTION_TERMINAL) {
        enter_sd_write_terminal(error);
        return;
    }

    atomic_set(&storage_health, SD_STORAGE_DEGRADED);
    sd_write_blocked = false;
    LOG_WRN("SD write degraded: failures_on_mount=%u remounts=%u next=%s error=%d",
            write_recovery_policy.failures_on_mount,
            write_recovery_policy.remounts,
            write_recovery_action == SD_WRITE_RECOVERY_ACTION_REMOUNT ? "remount" : "retry",
            error);
}

static void note_sd_write_success(void)
{
    if (atomic_get(&storage_health) == SD_STORAGE_TERMINAL) {
        return;
    }

    sd_write_recovery_on_success(&write_recovery_policy);
    write_recovery_action = SD_WRITE_RECOVERY_ACTION_RETRY;
    atomic_set(&storage_health, SD_STORAGE_HEALTHY);
    sd_write_blocked = false;
}

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
    current_batch_base_seq = base_seq;
    current_batch_packets = 0;
    current_batch_durable_packets = 0;
    current_batch_crc_protected = false;
    current_batch_loaded = true;
    current_batch_dirty = false;
    next_batch_flush_attempt_ms = 0;
}

static int sync_media(void)
{
    return disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_SYNC, NULL);
}

static bool meta_record_valid(const struct raw_meta_record *record)
{
    if (!record) {
        return false;
    }

    if (record->magic != RAW_META_MAGIC ||
        (record->version != RAW_META_LAYOUT_VERSION_LEGACY && record->version != RAW_META_LAYOUT_VERSION_CRC)) {
        return false;
    }

    if (record->write_seq < record->read_seq) {
        return false;
    }

    if ((record->write_seq - record->read_seq) > ring_state.capacity_packets) {
        return false;
    }

    if (record->version == RAW_META_LAYOUT_VERSION_CRC) {
        struct raw_meta_record crc_record = *record;
        uint32_t stored_crc = crc_record.metadata_crc32;
        crc_record.metadata_crc32 = 0U;
        uint32_t computed_crc = ring_transfer_crc32_update(0U, (const uint8_t *) &crc_record, sizeof(crc_record));
        if (stored_crc != computed_crc) {
            return false;
        }
    }

    return true;
}

static bool batch_header_valid(const struct raw_batch_header *header)
{
    if (!header) {
        return false;
    }

    if (header->magic != RAW_BATCH_MAGIC ||
        (header->version != RAW_BATCH_LAYOUT_VERSION_LEGACY && header->version != RAW_BATCH_LAYOUT_VERSION_CRC)) {
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

static uint32_t batch_payload_crc32(const uint8_t *buffer, const struct raw_batch_header *header)
{
    struct raw_batch_header crc_header = *header;
    crc_header.payload_crc32 = 0U;

    uint32_t crc = ring_transfer_crc32_update(0U, (const uint8_t *) &crc_header, sizeof(crc_header));
    size_t payload_bytes = (size_t) header->packet_count * RAW_AUDIO_PACKET_BYTES;
    return ring_transfer_crc32_update(crc, buffer + RAW_BATCH_HEADER_BYTES, payload_bytes);
}

static bool batch_payload_valid(const uint8_t *buffer, const struct raw_batch_header *header)
{
    if (header->version == RAW_BATCH_LAYOUT_VERSION_LEGACY) {
        return true;
    }
    return batch_payload_crc32(buffer, header) == header->payload_crc32;
}

static int persist_ring_metadata(const sd_ring_info_t *state, ring_metadata_authority_t authority)
{
    if (!state) {
        return -EINVAL;
    }

    /*
     * A write-ahead quarantine binds its baseline cursor to one metadata
     * generation. No unrelated mutation may advance that generation until
     * the owner transaction commits or reboot recovery reconciles it.
     */
    if (authority == RING_METADATA_RUNTIME_MUTATION && app_settings_get_sd_ring_quarantine().active) {
        return -EBUSY;
    }

    struct raw_meta_record record;
    memset(&record, 0, sizeof(record));
    record.magic = RAW_META_MAGIC;
    record.version = RAW_META_LAYOUT_VERSION_CRC;
    record.generation = ++meta_generation;
    record.read_seq = state->read_seq;
    record.write_seq = state->write_seq;
    record.dropped_packets = state->dropped_packets;
    record.metadata_crc32 = ring_transfer_crc32_update(0U, (const uint8_t *) &record, sizeof(record));

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

static int reconcile_corrupt_batch_window(uint64_t batch_start_seq, uint32_t batch_packets, const char *reason)
{
    sd_ring_info_t previous = ring_state;
    int changed = sd_ring_reconcile_corrupt_batch(&ring_state, batch_start_seq, batch_packets);
    if (changed <= 0) {
        return changed;
    }

    int ret = persist_ring_metadata(&ring_state, RING_METADATA_RUNTIME_MUTATION);
    if (ret == 0) {
        ret = sync_media();
    }
    if (ret < 0) {
        ring_state = previous;
        LOG_ERR(
            "failed to persist corrupt-batch reconciliation at %llu: %d", (unsigned long long) batch_start_seq, ret);
        return ret;
    }

    invalidate_read_batch_cache();
    sd_ring_durability_init(&ring_durability, &ring_state);
    LOG_ERR("quarantined corrupt SD batch at %llu (%s): read=%llu write=%llu dropped=%llu",
            (unsigned long long) batch_start_seq,
            reason,
            (unsigned long long) ring_state.read_seq,
            (unsigned long long) ring_state.write_seq,
            (unsigned long long) ring_state.dropped_packets);
    return 1;
}

static int load_ring_metadata(void)
{
    struct raw_meta_record best_record = {0};
    bool found = false;
    uint32_t best_slot = 0;

    for (uint32_t slot = 0; slot < RAW_META_SECTORS; slot++) {
        int ret = disk_access_read(DISK_DRIVE_NAME, sector_buffer, slot, 1);
        if (ret != 0) {
            LOG_WRN("metadata read failed at slot %u: %d", slot, ret);
            continue;
        }

        struct raw_meta_record record;
        memcpy(&record, sector_buffer, sizeof(record));
        if (!meta_record_valid(&record)) {
            continue;
        }

        if (!found || record.generation > best_record.generation) {
            best_record = record;
            best_slot = slot;
            found = true;
        }
    }

    if (!found) {
        ring_state.read_seq = 0;
        ring_state.write_seq = 0;
        ring_state.dropped_packets = 0;
        meta_generation = 0;
        meta_next_slot = 0;
        return persist_ring_metadata(&ring_state, RING_METADATA_RUNTIME_MUTATION);
    }

    ring_state.read_seq = best_record.read_seq;
    ring_state.write_seq = best_record.write_seq;
    ring_state.dropped_packets = best_record.dropped_packets;
    meta_generation = best_record.generation;
    meta_next_slot = (best_slot + 1U) % RAW_META_SECTORS;
    return 0;
}

static int load_batch_for_seq(uint64_t seq, uint8_t *buffer, struct raw_batch_header *header, bool repair_stale_window)
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
        return -EIO;
    }

    memcpy(header, buffer, sizeof(*header));
    if (!batch_header_valid(header)) {
        LOG_ERR("invalid batch header for seq %llu", (unsigned long long) seq);
        if (repair_stale_window) {
            int repair_ret = reconcile_corrupt_batch_window(base_seq, RAW_PACKETS_PER_BATCH, "invalid header");
            return repair_ret < 0 ? repair_ret : -ERANGE;
        }
        return -EIO;
    }

    if (!batch_payload_valid(buffer, header)) {
        LOG_ERR("batch CRC mismatch for seq %llu", (unsigned long long) seq);
        if (repair_stale_window) {
            int repair_ret = reconcile_corrupt_batch_window(base_seq, RAW_PACKETS_PER_BATCH, "payload CRC");
            return repair_ret < 0 ? repair_ret : -ERANGE;
        }
        return -EIO;
    }

    if (header->start_seq != base_seq) {
        if (repair_stale_window) {
            int repair_ret = reconcile_corrupt_batch_window(base_seq, RAW_PACKETS_PER_BATCH, "stale physical slot");
            return repair_ret < 0 ? repair_ret : -ERANGE;
        }

        LOG_ERR("batch start mismatch for seq %llu: hdr=%llu base=%llu",
                (unsigned long long) seq,
                (unsigned long long) header->start_seq,
                (unsigned long long) base_seq);
        return -EIO;
    }

    if (buffer != batch_read_buffer) {
        memcpy(batch_read_buffer, buffer, sizeof(batch_read_buffer));
    }
    cached_read_batch_base_seq = base_seq;
    cached_read_batch_header = *header;
    cached_read_batch_valid = true;

    return 0;
}

static bool crc_batch_is_valid_at_base(const uint8_t *buffer, uint64_t expected_base)
{
    struct raw_batch_header header;
    memcpy(&header, buffer, sizeof(header));
    return batch_header_valid(&header) && header.version == RAW_BATCH_LAYOUT_VERSION_CRC &&
           header.start_seq == expected_base && batch_payload_valid(buffer, &header);
}

static int reconcile_persisted_quarantine(void)
{
    int load_error = app_settings_get_sd_ring_quarantine_load_error();
    if (load_error < 0) {
        LOG_ERR("SD quarantine intent failed validation: %d", load_error);
        return load_error;
    }

    app_sd_ring_quarantine_t marker = app_settings_get_sd_ring_quarantine();
    if (!marker.active) {
        return 0;
    }
    if (marker.batch_packets != RAW_PACKETS_PER_BATCH) {
        LOG_ERR("invalid persisted SD quarantine span: %u", marker.batch_packets);
        return -EINVAL;
    }
    if (marker.capacity_packets != ring_state.capacity_packets || marker.metadata_generation > meta_generation) {
        LOG_ERR("persisted SD quarantine identity mismatch: capacity=%u/%u generation=%llu/%llu",
                marker.capacity_packets,
                ring_state.capacity_packets,
                (unsigned long long) marker.metadata_generation,
                (unsigned long long) meta_generation);
        return -EINVAL;
    }

    bool batch_valid = false;
    bool preimage_untouched = false;
    if (data_batch_count != 0U) {
        uint32_t sector = batch_sector_for_base_seq(marker.replacement_start_seq);
        int read_ret = disk_access_read(DISK_DRIVE_NAME, batch_read_buffer, sector, RAW_BATCH_SECTORS);
        if (read_ret == 0) {
            uint32_t physical_crc = ring_transfer_crc32_update(0U, batch_read_buffer, sizeof(batch_read_buffer));
            preimage_untouched = physical_crc == marker.preimage_crc32;
            batch_valid = crc_batch_is_valid_at_base(batch_read_buffer, marker.replacement_start_seq);
        }
    }

    sd_ring_info_t previous = ring_state;
    sd_ring_quarantine_recovery_t recovery = {
        .affected_start_seq = marker.affected_start_seq,
        .replacement_start_seq = marker.replacement_start_seq,
        .attempted_write_seq = marker.attempted_write_seq,
        .metadata_generation = marker.metadata_generation,
        .baseline =
            {
                .read_seq = marker.baseline_read_seq,
                .write_seq = marker.baseline_write_seq,
                .dropped_packets = marker.baseline_dropped_packets,
                .capacity_packets = marker.capacity_packets,
            },
        .batch_packets = marker.batch_packets,
        .preimage_untouched = preimage_untouched,
        .replacement_valid = batch_valid,
    };
    int reconcile_ret = sd_ring_reconcile_quarantine(&ring_state, meta_generation, &recovery);
    if (reconcile_ret < 0) {
        return reconcile_ret;
    }

    if (reconcile_ret > 0) {
        int persist_ret = persist_ring_metadata(&ring_state, RING_METADATA_QUARANTINE_RECOVERY);
        if (persist_ret == 0) {
            persist_ret = sync_media();
        }
        if (persist_ret < 0) {
            ring_state = previous;
            return persist_ret;
        }
        sd_ring_durability_init(&ring_durability, &ring_state);
        LOG_ERR("reconciled persisted SD quarantine: read=%llu write=%llu dropped=%llu",
                (unsigned long long) ring_state.read_seq,
                (unsigned long long) ring_state.write_seq,
                (unsigned long long) ring_state.dropped_packets);
    }

    int clear_ret = app_settings_clear_sd_ring_quarantine();
    if (clear_ret < 0) {
        /* Leaving a stale marker is conservative: the next boot validates it again. */
        LOG_ERR("could not clear reconciled SD quarantine: %d", clear_ret);
    }
    invalidate_read_batch_cache();
    return 0;
}

static int validate_mounted_batch(uint64_t seq)
{
    struct raw_batch_header header;
    int ret = load_batch_for_seq(seq, batch_read_buffer, &header, true);
    return ret == -ERANGE ? 0 : ret;
}

static int validate_mounted_ring_edges(void)
{
    if (ring_state.read_seq == ring_state.write_seq) {
        return 0;
    }

    int ret = validate_mounted_batch(ring_state.read_seq);
    if (ret < 0 || ring_state.read_seq == ring_state.write_seq) {
        return ret;
    }

    uint64_t tail_seq = ring_state.write_seq - 1U;
    uint64_t head_base = (ring_state.read_seq / RAW_PACKETS_PER_BATCH) * RAW_PACKETS_PER_BATCH;
    uint64_t tail_base = (tail_seq / RAW_PACKETS_PER_BATCH) * RAW_PACKETS_PER_BATCH;
    if (tail_base != head_base) {
        ret = validate_mounted_batch(tail_seq);
    }
    return ret;
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
    int ret = load_batch_for_seq(base_seq, current_batch, &header, true);
    if (ret < 0) {
        LOG_WRN("dropping incomplete tail batch after recovery error: %d", ret);
        if (ret == -ERANGE) {
            start_empty_batch(ring_state.write_seq);
            return 0;
        }
        return ret;
    }

    uint16_t restored_packets = (uint16_t) partial_packets;
    if (header.packet_count < partial_packets) {
        uint32_t lost_packets = partial_packets - header.packet_count;
        LOG_WRN("tail packet count below metadata, truncating %u -> %u", partial_packets, header.packet_count);
        ring_state.write_seq = header.start_seq + header.packet_count;
        if (ring_state.read_seq > ring_state.write_seq) {
            ring_state.read_seq = ring_state.write_seq;
        }
        ring_state.dropped_packets += lost_packets;
        restored_packets = header.packet_count;
        ret = persist_ring_metadata(&ring_state, RING_METADATA_RUNTIME_MUTATION);
        if (ret == 0) {
            ret = sync_media();
        }
        if (ret < 0) {
            return ret;
        }
    } else if (header.packet_count > partial_packets) {
        uint32_t uncommitted_packets = header.packet_count - partial_packets;
        LOG_WRN("ignoring %u CRC-valid tail packet(s) beyond durable metadata", uncommitted_packets);
    }

    current_batch_base_seq = header.start_seq;
    current_batch_packets = restored_packets;
    current_batch_durable_packets = restored_packets;
    current_batch_crc_protected = header.version == RAW_BATCH_LAYOUT_VERSION_CRC;
    current_batch_loaded = true;
    current_batch_dirty = false;
    return 0;
}

static void retain_current_batch_for_retry(void)
{
    next_batch_flush_attempt_ms = k_uptime_get() + RAW_FLUSH_INTERVAL_MS;
}

struct ring_commit_context {
    uint32_t batch_sector;
    bool owns_quarantine;
};

static int write_current_batch_payload(void *context)
{
    const struct ring_commit_context *commit = context;
    if (!commit) {
        return -EINVAL;
    }

    /*
     * Crash ordering for CRC-v2 batches:
     *   payload sectors -> barrier -> header/CRC sector last.
     * An old v2 header then detects a torn payload; a legacy v1 tail is
     * protected by the one-time MCU-NVS quarantine armed before this call.
     */
    int ret = disk_access_write(
        DISK_DRIVE_NAME, current_batch + DISK_SECTOR_SIZE, commit->batch_sector + 1U, RAW_BATCH_SECTORS - 1U);
    return ret == 0 ? 0 : -EIO;
}

static int write_current_batch_header(void *context)
{
    const struct ring_commit_context *commit = context;
    if (!commit) {
        return -EINVAL;
    }

    int ret = disk_access_write(DISK_DRIVE_NAME, current_batch, commit->batch_sector, 1U);
    return ret == 0 ? 0 : -EIO;
}

static int persist_candidate_metadata(const sd_ring_cursor_t *candidate, void *context)
{
    const struct ring_commit_context *commit = context;
    ring_metadata_authority_t authority =
        commit && commit->owns_quarantine ? RING_METADATA_QUARANTINE_OWNER : RING_METADATA_RUNTIME_MUTATION;
    return persist_ring_metadata(candidate, authority);
}

static int sync_candidate_media(void *context)
{
    ARG_UNUSED(context);
    return sync_media();
}

static const sd_ring_durability_ops_t ring_durability_ops = {
    .write_payload = write_current_batch_payload,
    .write_header = write_current_batch_header,
    .persist_metadata = persist_candidate_metadata,
    .sync_media = sync_candidate_media,
};

static int arm_legacy_batch_quarantine(const sd_ring_info_t *candidate, bool *armed)
{
    if (!candidate || !armed) {
        return -EINVAL;
    }
    *armed = false;

    bool rewrites_durable_tail = current_batch_durable_packets > 0U;
    if (!rewrites_durable_tail || current_batch_crc_protected) {
        return 0;
    }

    uint64_t affected_start_seq = current_batch_base_seq;

    app_sd_ring_quarantine_t existing = app_settings_get_sd_ring_quarantine();
    if (existing.active) {
        bool same_transaction = existing.affected_start_seq == affected_start_seq &&
                                existing.replacement_start_seq == current_batch_base_seq &&
                                existing.capacity_packets == ring_durability.durable.capacity_packets &&
                                existing.batch_packets == RAW_PACKETS_PER_BATCH &&
                                existing.baseline_read_seq == ring_durability.durable.read_seq &&
                                existing.baseline_write_seq == ring_durability.durable.write_seq &&
                                existing.baseline_dropped_packets == ring_durability.durable.dropped_packets;
        if (!same_transaction ||
            !sd_ring_quarantine_retry_allowed(existing.attempted_write_seq, candidate->write_seq)) {
            return -EIO;
        }
        *armed = true;
        return 0;
    }

    uint32_t sector = batch_sector_for_base_seq(current_batch_base_seq);
    int read_ret = disk_access_read(DISK_DRIVE_NAME, batch_read_buffer, sector, RAW_BATCH_SECTORS);
    if (read_ret != 0) {
        return -EIO;
    }

    struct raw_batch_header preimage_header;
    memcpy(&preimage_header, batch_read_buffer, sizeof(preimage_header));
    bool preimage_crc_protected =
        batch_header_valid(&preimage_header) && preimage_header.version == RAW_BATCH_LAYOUT_VERSION_CRC &&
        preimage_header.start_seq == affected_start_seq && batch_payload_valid(batch_read_buffer, &preimage_header);
    if (preimage_crc_protected) {
        invalidate_read_batch_cache();
        return 0;
    }

    uint32_t preimage_crc32 = ring_transfer_crc32_update(0U, batch_read_buffer, sizeof(batch_read_buffer));
    int save_ret = app_settings_save_sd_ring_quarantine(affected_start_seq,
                                                        current_batch_base_seq,
                                                        candidate->write_seq,
                                                        meta_generation,
                                                        ring_durability.durable.read_seq,
                                                        ring_durability.durable.write_seq,
                                                        ring_durability.durable.dropped_packets,
                                                        ring_durability.durable.capacity_packets,
                                                        RAW_PACKETS_PER_BATCH,
                                                        preimage_crc32);
    invalidate_read_batch_cache();
    if (save_ret < 0) {
        return save_ret;
    }

    *armed = true;
    return 0;
}

static int persist_wrap_safe_floor(const sd_ring_info_t *candidate)
{
    if (candidate->read_seq <= ring_durability.durable.read_seq) {
        return 0;
    }

    sd_ring_info_t safe_floor = ring_durability.durable;
    safe_floor.read_seq = candidate->read_seq;
    safe_floor.dropped_packets = candidate->dropped_packets;
    bool quarantine_active = app_settings_get_sd_ring_quarantine().active;
    int ret = sd_ring_durability_commit_metadata(
        &ring_durability, &safe_floor, quarantine_active, true, &ring_durability_ops, NULL);
    if (ret < 0) {
        return ret;
    }

    /*
     * The aliased victim is no longer advertised before payload sector 1 can
     * be touched. A reset or failed batch write therefore cannot resurrect it.
     */
    ring_state = ring_durability.durable;
    return 0;
}

static int flush_current_batch(bool sync_requested)
{
    /* SD is powered off (idle): keep the batch buffered in RAM, do not touch the
     * disk. It will be flushed after the next remount. */
    if (!is_mounted) {
        return sync_requested ? -ENODEV : 0;
    }

    if (!current_batch_loaded || !current_batch_dirty || current_batch_packets == 0U) {
        if (app_settings_get_sd_ring_quarantine().active) {
            int clear_ret = app_settings_clear_sd_ring_quarantine();
            if (clear_ret < 0) {
                return clear_ret;
            }
        }
        if (sync_requested) {
            int sync_ret = sync_media();
            if (sync_ret < 0) {
                note_sd_write_failure(sync_ret);
                LOG_ERR("media sync failed with no dirty batch: %d", sync_ret);
                return sync_ret;
            }
            note_sd_write_success();
        }
        return 0;
    }

    sd_ring_info_t candidate = ring_durability.durable;
    uint64_t new_write_seq = current_batch_base_seq + current_batch_packets;

    if (candidate.write_seq <= current_batch_base_seq && current_batch_base_seq >= candidate.capacity_packets) {
        uint64_t overwritten_end_seq = current_batch_base_seq - candidate.capacity_packets + RAW_PACKETS_PER_BATCH;
        if (candidate.read_seq < overwritten_end_seq) {
            candidate.dropped_packets += overwritten_end_seq - candidate.read_seq;
            candidate.read_seq = overwritten_end_seq;
        }
    }

    if ((new_write_seq - candidate.read_seq) > candidate.capacity_packets) {
        uint64_t overflow = (new_write_seq - candidate.read_seq) - candidate.capacity_packets;
        candidate.read_seq += overflow;
        candidate.dropped_packets += overflow;
    }
    candidate.write_seq = new_write_seq;

    int floor_ret = persist_wrap_safe_floor(&candidate);
    if (floor_ret < 0) {
        retain_current_batch_for_retry();
        note_sd_write_failure(floor_ret);
        LOG_ERR("refusing wrap write before durable victim-floor commit: %d", floor_ret);
        return floor_ret;
    }

    struct raw_batch_header header = {
        .magic = RAW_BATCH_MAGIC,
        .version = RAW_BATCH_LAYOUT_VERSION_CRC,
        .packet_count = current_batch_packets,
        .generation = meta_generation + 1U,
        .start_seq = current_batch_base_seq,
        .payload_crc32 = 0U,
    };
    memcpy(current_batch, &header, sizeof(header));
    header.payload_crc32 = batch_payload_crc32(current_batch, &header);
    memcpy(current_batch, &header, sizeof(header));

    bool quarantine_armed = false;
    int quarantine_ret = arm_legacy_batch_quarantine(&candidate, &quarantine_armed);
    if (quarantine_ret < 0) {
        retain_current_batch_for_retry();
        note_sd_write_failure(quarantine_ret);
        LOG_ERR("refusing destructive SD write without durable quarantine: %d", quarantine_ret);
        return quarantine_ret;
    }

    struct ring_commit_context commit = {
        .batch_sector = batch_sector_for_base_seq(current_batch_base_seq),
        .owns_quarantine = quarantine_armed,
    };
    int ret = sd_ring_durability_commit_batch(
        &ring_durability, &candidate, current_batch_base_seq, true, &ring_durability_ops, &commit);
    if (ret < 0) {
        ring_state = ring_durability.durable;
        retain_current_batch_for_retry();
        note_sd_write_failure(ret);
        LOG_ERR("batch durability transaction failed at sector %u: %d", commit.batch_sector, ret);
        return ret;
    }

    ring_state = ring_durability.durable;
    current_batch_dirty = false;
    current_batch_durable_packets = current_batch_packets;
    current_batch_crc_protected = true;
    invalidate_read_batch_cache();
    note_sd_write_success();
    next_batch_flush_attempt_ms = 0;

    if (quarantine_armed) {
        int clear_ret = app_settings_clear_sd_ring_quarantine();
        if (clear_ret < 0) {
            /* The stale marker is safe and self-reconciles on the next boot. */
            LOG_ERR("SD commit durable but quarantine clear failed: %d", clear_ret);
        }
    }

    if (current_batch_packets >= RAW_PACKETS_PER_BATCH) {
        start_empty_batch(ring_state.write_seq);
    }

    return 0;
}

static int clear_ring_internal(bool sync_requested)
{
    sd_ring_info_t candidate = ring_durability.durable;
    candidate.read_seq = 0;
    candidate.write_seq = 0;
    candidate.dropped_packets = 0;

    bool quarantine_active = app_settings_get_sd_ring_quarantine().active;
    int ret = sd_ring_durability_commit_metadata(
        &ring_durability, &candidate, quarantine_active, sync_requested, &ring_durability_ops, NULL);
    if (ret < 0) {
        return ret;
    }

    ring_state = ring_durability.durable;
    compat_current_name[0] = '\0';
    compat_saved_name[0] = '\0';
    compat_saved_offset = 0;
    invalidate_read_batch_cache();
    start_empty_batch(0);

    return 0;
}

static int read_packets_internal(uint64_t start_seq,
                                 uint8_t *out_buf,
                                 uint32_t max_bytes,
                                 uint32_t *bytes_read,
                                 uint32_t *packets_read,
                                 bool flush_dirty_tail)
{
    if (!out_buf || !bytes_read || !packets_read) {
        return -EINVAL;
    }

    *bytes_read = 0;
    *packets_read = 0;

    if (!is_mounted) {
        return -ENODEV;
    }

    if (flush_dirty_tail && current_batch_dirty) {
        int flush_ret = flush_current_batch(false);
        if (flush_ret < 0) {
            return flush_ret;
        }
    }

    if (max_bytes < RAW_AUDIO_PACKET_BYTES) {
        return 0;
    }

    uint32_t max_packets = max_bytes / RAW_AUDIO_PACKET_BYTES;
    sd_ring_read_plan_t plan;
    int plan_ret = sd_ring_durability_plan_read(&ring_durability, start_seq, max_packets, &plan);
    if (plan_ret < 0) {
        return plan_ret;
    }
    max_packets = plan.packet_count;

    uint64_t seq = plan.start_seq;
    uint32_t copied_packets = 0;
    uint64_t loaded_batch_base = UINT64_MAX;
    struct raw_batch_header loaded_header = {0};

    while (copied_packets < max_packets) {
        uint64_t batch_base = (seq / RAW_PACKETS_PER_BATCH) * RAW_PACKETS_PER_BATCH;
        if (batch_base != loaded_batch_base) {
            int ret = load_batch_for_seq(seq, batch_read_buffer, &loaded_header, flush_dirty_tail);
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

static int advance_read_seq_durably_internal(uint64_t new_read_seq)
{
    const sd_ring_info_t durable = ring_durability.durable;
    if (new_read_seq < durable.read_seq || new_read_seq > durable.write_seq) {
        return -ERANGE;
    }

    if (new_read_seq == durable.read_seq) {
        return 0;
    }

    sd_ring_info_t candidate = durable;
    candidate.read_seq = new_read_seq;
    bool quarantine_active = app_settings_get_sd_ring_quarantine().active;
    int ret = sd_ring_durability_commit_metadata(
        &ring_durability, &candidate, quarantine_active, true, &ring_durability_ops, NULL);
    if (ret < 0) {
        LOG_ERR("failed to durably advance read watermark: %d", ret);
        return ret;
    }

    ring_state = ring_durability.durable;
    return 0;
}

static bool process_write_data_req(const sd_req_t *req)
{
    if (!req) {
        return true;
    }

    /*
     * Freeze producer ownership while a legacy write-ahead quarantine is
     * unresolved. Otherwise a reset could lose later accepted records that
     * were never included in the persisted attempted_write_seq.
     */
    if (app_settings_get_sd_ring_quarantine().active) {
        sd_set_io_low_power(false);
        int marker_flush_ret = flush_current_batch(false);
        sd_set_io_low_power(true);
        if (marker_flush_ret < 0) {
            return false;
        }
    }

    /*
     * Do not stage accepted audio in current_batch while the card is
     * unmounted. A later successful sd_mount() restores the on-media tail into
     * that same buffer and would overwrite the staged records. The retained
     * request path remounts first, then retries this exact request.
     */
    if (!is_mounted) {
        return false;
    }

    if (req->u.write.len != MAX_WRITE_SIZE) {
        LOG_ERR("unexpected accepted write size %u", (unsigned) req->u.write.len);
        return true;
    }

    if (!current_batch_loaded) {
        start_empty_batch(ring_state.write_seq);
    }

    if (current_batch_packets >= RAW_PACKETS_PER_BATCH) {
        sd_set_io_low_power(false);
        int ret = flush_current_batch(false);
        sd_set_io_low_power(true);
        if (ret < 0 || current_batch_packets >= RAW_PACKETS_PER_BATCH) {
            /*
             * This request has already been accepted by write_to_file(), but
             * has not been copied into the batch. Its caller must retain and
             * retry this exact request before dequeuing newer audio.
             */
            return false;
        }
    }

    size_t dst_offset = RAW_BATCH_HEADER_BYTES + ((size_t) current_batch_packets * RAW_AUDIO_PACKET_BYTES);
    sys_put_be32(req->u.write.timestamp, current_batch + dst_offset);
    memcpy(current_batch + dst_offset + RAW_AUDIO_TIMESTAMP_BYTES, req->u.write.buf, MAX_WRITE_SIZE);
    current_batch_packets++;
    current_batch_dirty = true;
    next_batch_flush_attempt_ms = k_uptime_get() + RAW_FLUSH_INTERVAL_MS;
    format_timestamp_name(req->u.write.timestamp, compat_current_name, sizeof(compat_current_name));

    bool queue_pressure_high = k_msgq_num_used_get(&sd_msgq) >= (SD_REQ_QUEUE_MSGS / 3);
    if (current_batch_packets >= RAW_PACKETS_PER_BATCH || queue_pressure_high) {
        sd_set_io_low_power(false);
        int ret = flush_current_batch(false);
        sd_set_io_low_power(true);
        if (ret < 0) {
            LOG_ERR("accepted audio retained in dirty batch after flush failure: %d", ret);
        }
    }

    return true;
}

static bool process_or_retain_accepted_write(const sd_req_t *req)
{
    if (atomic_get(&storage_health) == SD_STORAGE_TERMINAL) {
        record_terminal_at_risk_records(1U, "accepted write");
        return true;
    }

    if (process_write_data_req(req)) {
        return true;
    }

    if (atomic_get(&storage_health) == SD_STORAGE_TERMINAL) {
        record_terminal_at_risk_records(1U, "retained write");
        return true;
    }

    retained_write_req = *req;
    retained_write_pending = true;
    retained_write_retry_delay_ms =
        retained_write_retry_delay_ms == 0U ? 50U : MIN(retained_write_retry_delay_ms * 2U, RAW_FLUSH_INTERVAL_MS);
    retained_write_retry_deadline_ms = k_uptime_get() + retained_write_retry_delay_ms;
    return false;
}

static bool retry_retained_write(bool force)
{
    if (!retained_write_pending) {
        return true;
    }

    if (atomic_get(&storage_health) == SD_STORAGE_TERMINAL) {
        record_terminal_at_risk_records(1U, "retained write");
        retained_write_pending = false;
        retained_write_retry_delay_ms = 0U;
        retained_write_retry_deadline_ms = 0;
        return true;
    }

    int64_t now = k_uptime_get();
    if (!force && now < retained_write_retry_deadline_ms) {
        return false;
    }

    if (write_recovery_action == SD_WRITE_RECOVERY_ACTION_REMOUNT) {
        int recovery_ret = recover_sd_media_preserving_ram();
        if (recovery_ret < 0) {
            note_sd_write_failure(recovery_ret);
            retained_write_retry_deadline_ms = now + retained_write_retry_delay_ms;
            return false;
        }
        write_recovery_action = SD_WRITE_RECOVERY_ACTION_RETRY;
    }

    if (!is_mounted) {
        int mount_ret = mount_for_pending_write();
        if (mount_ret < 0) {
            note_sd_write_failure(mount_ret);
            retained_write_retry_deadline_ms = now + retained_write_retry_delay_ms;
            return false;
        }
    }

    if (atomic_get(&storage_health) == SD_STORAGE_TERMINAL) {
        record_terminal_at_risk_records(1U, "retained write");
        retained_write_pending = false;
        retained_write_retry_delay_ms = 0U;
        retained_write_retry_deadline_ms = 0;
        return true;
    }

    if (!is_mounted) {
        retained_write_retry_deadline_ms = now + retained_write_retry_delay_ms;
        return false;
    }

    if (!process_write_data_req(&retained_write_req)) {
        retained_write_retry_delay_ms =
            MIN(retained_write_retry_delay_ms == 0U ? 50U : retained_write_retry_delay_ms * 2U, RAW_FLUSH_INTERVAL_MS);
        retained_write_retry_deadline_ms = k_uptime_get() + retained_write_retry_delay_ms;
        return false;
    }

    retained_write_pending = false;
    retained_write_retry_delay_ms = 0U;
    retained_write_retry_deadline_ms = 0;
    return true;
}

static int drain_pending_write_queue(void)
{
    if (!retry_retained_write(true)) {
        return -EAGAIN;
    }

    while (1) {
        sd_req_t pending_req;
        if (k_msgq_get(&sd_msgq, &pending_req, K_NO_WAIT) != 0) {
            break;
        }

        if (pending_req.type == REQ_WRITE_DATA) {
            if (!process_or_retain_accepted_write(&pending_req)) {
                return -EAGAIN;
            }
        }
    }

    return 0;
}

static int commit_pending_writes_for_snapshot(void)
{
    int drain_ret = drain_pending_write_queue();
    if (drain_ret < 0) {
        return drain_ret;
    }
    if (!current_batch_dirty) {
        return 0;
    }

    return flush_current_batch(false);
}

static sd_ring_info_t ring_info_with_terminal_losses(void)
{
    return sd_ring_durability_info(&ring_durability);
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

static int sd_mount_internal(bool restore_ring_state)
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

    uint32_t mounted_batch_count = (disk_sector_count - RAW_META_SECTORS) / RAW_BATCH_SECTORS;
    if (mounted_batch_count == 0U) {
        LOG_ERR("not enough sectors for raw ring layout");
        sd_enable_power(false);
        return -ENOSPC;
    }

    if (!restore_ring_state && data_batch_count != 0U && mounted_batch_count != data_batch_count) {
        LOG_ERR(
            "SD geometry changed during write recovery: batches=%u expected=%u", mounted_batch_count, data_batch_count);
        sd_enable_power(false);
        return -EIO;
    }

    data_batch_count = mounted_batch_count;
    ring_state.capacity_packets = data_batch_count * RAW_PACKETS_PER_BATCH;

    if (restore_ring_state) {
        ret = load_ring_metadata();
        if (ret < 0) {
            LOG_ERR("failed to load raw ring metadata: %d", ret);
            sd_enable_power(false);
            return ret;
        }

        ret = reconcile_persisted_quarantine();
        if (ret < 0) {
            LOG_ERR("failed to reconcile persisted SD quarantine: %d", ret);
            sd_enable_power(false);
            return ret;
        }

        ret = validate_mounted_ring_edges();
        if (ret < 0) {
            LOG_ERR("failed to validate mounted SD ring edges: %d", ret);
            sd_enable_power(false);
            return ret;
        }

        ret = restore_tail_batch();
        if (ret < 0) {
            LOG_ERR("failed to restore durable SD tail: %d", ret);
            sd_enable_power(false);
            return ret;
        }
        sd_ring_durability_init(&ring_durability, &ring_state);
    }

    is_mounted = true;

    LOG_INF("Raw SD ring mounted: sectors=%u, batches=%u, capacity=%u packets",
            disk_sector_count,
            data_batch_count,
            ring_state.capacity_packets);
    return 0;
}

static int sd_mount(void)
{
    return sd_mount_internal(true);
}

static int recover_sd_media_preserving_ram(void)
{
    LOG_WRN("Power-cycling SD while retaining the dirty batch in RAM (remount %u/%u)",
            write_recovery_policy.remounts,
            SD_WRITE_MAX_REMOUNTS);

    sd_set_io_low_power(false);
    if (is_mounted) {
        int deinit_ret = disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_DEINIT, NULL);
        if (deinit_ret < 0) {
            LOG_WRN("SD recovery deinit failed: %d", deinit_ret);
        }
        is_mounted = false;
    }

    int power_ret = sd_enable_power(false);
    if (power_ret < 0) {
        return power_ret;
    }

    k_msleep(50);
    gpio_pin_set_raw(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 11, 1);
    int mount_ret = sd_mount_internal(false);
    if (mount_ret < 0) {
        LOG_ERR("SD recovery remount failed: %d", mount_ret);
        return mount_ret;
    }

    LOG_INF("SD recovery remount succeeded; retrying retained data");
    return 0;
}

static int deinit_mounted_media_without_flush(void)
{
    if (!is_mounted) {
        return 0;
    }

    int ret = disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_DEINIT, NULL);
    if (ret < 0) {
        LOG_ERR("SD terminal deinit failed: %d", ret);
        return ret;
    }

    is_mounted = false;
    return 0;
}

static int sd_unmount(void)
{
    int ret = flush_current_batch(true);
    if (ret < 0) {
        LOG_ERR("Raw SD ring unmount aborted: flush/sync failed: %d", ret);
        return ret;
    }

    if (is_mounted) {
        ret = disk_access_ioctl(DISK_DRIVE_NAME, DISK_IOCTL_CTRL_DEINIT, NULL);
        if (ret < 0) {
            LOG_ERR("Raw SD ring unmount aborted: deinit failed: %d", ret);
            return ret;
        }
        is_mounted = false;
    }

    ret = sd_enable_power(false);
    if (ret < 0) {
        LOG_ERR("Raw SD ring power-off failed: %d", ret);
        return ret;
    }
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

    int res;
    bool boot_terminal = false;
    while ((res = sd_mount()) != 0) {
        sd_boot_mount_outcome_t outcome = sd_write_recovery_boot_mount_result(&write_recovery_policy, res);
        if (outcome == SD_BOOT_MOUNT_TERMINAL) {
            enter_sd_write_terminal(res);
            boot_terminal = true;
            break;
        }

        atomic_set(&storage_health, SD_STORAGE_DEGRADED);
        write_recovery_action = SD_WRITE_RECOVERY_ACTION_REMOUNT;
        LOG_ERR("[SD_WORK] full boot mount failed: %d; remount %u/%u",
                res,
                write_recovery_policy.remounts,
                SD_WRITE_MAX_REMOUNTS);
        if (sd_shutdown_in_progress) {
            return;
        }
        k_msleep(SD_POWER_ON_RETRY_MS);
    }

    atomic_clear(&pending_power_on);
    atomic_set(&sd_boot_ready, 1);
    if (boot_terminal) {
        LOG_ERR("[SD_BOOT] storage unavailable after bounded mount recovery; live BLE remains available");
    } else {
        note_sd_write_success();
        LOG_INF("[SD_BOOT] raw ring ready (used=%llu bytes)", (unsigned long long) ring_used_bytes());
        sd_set_io_low_power(true);
    }

    while (1) {
        if (atomic_get(&pending_power_on)) {
            if (!atomic_get(&desired_sd_power_on) || sd_shutdown_in_progress) {
                atomic_clear(&pending_power_on);
            } else if (k_uptime_get() >= power_on_retry_deadline_ms) {
                atomic_clear(&pending_power_on);
                req.type = REQ_POWER_ON;
                goto handle_req;
            }
        }

        if (atomic_cas(&pending_flush_on_ble_connect, 1, 0)) {
            req.type = REQ_FLUSH;
            req.u.status.resp = NULL;
            goto handle_req;
        }

        if (k_msgq_get(&sd_prio_msgq, &req, K_NO_WAIT) == 0) {
            goto handle_req;
        }

        if (atomic_get(&pending_idle_power_off) && !atomic_get(&desired_sd_power_on) &&
            k_uptime_get() >= idle_power_off_retry_deadline_ms) {
            atomic_clear(&pending_idle_power_off);
            req.type = REQ_POWER_OFF;
            goto handle_req;
        }

        if (!retained_write_pending && current_batch_dirty &&
            write_recovery_action == SD_WRITE_RECOVERY_ACTION_REMOUNT &&
            k_uptime_get() >= next_batch_flush_attempt_ms) {
            int recovery_ret = recover_sd_media_preserving_ram();
            if (recovery_ret < 0) {
                note_sd_write_failure(recovery_ret);
                next_batch_flush_attempt_ms = k_uptime_get() + RAW_FLUSH_INTERVAL_MS;
            } else {
                write_recovery_action = SD_WRITE_RECOVERY_ACTION_RETRY;
            }
        }

        if (retained_write_pending) {
            (void) retry_retained_write(false);
            if (retained_write_pending) {
                int64_t retry_wait_ms = retained_write_retry_deadline_ms - k_uptime_get();
                retry_wait_ms = CLAMP(retry_wait_ms, 1, 250);
                if (k_msgq_get(&sd_prio_msgq, &req, K_MSEC(retry_wait_ms)) == 0) {
                    goto handle_req;
                }
                continue;
            }
        }

        k_timeout_t write_wait = ble_connected ? K_MSEC(50) : K_MSEC(250);
        if (k_msgq_get(&sd_msgq, &req, write_wait) != 0) {
            int64_t now = k_uptime_get();
            if (ring_storage_flush_retry_due(current_batch_dirty, now, next_batch_flush_attempt_ms)) {
                sd_set_io_low_power(false);
                if (sd_write_recovery_mount_required(current_batch_dirty, is_mounted, &write_recovery_policy)) {
                    int mount_ret = mount_for_pending_write();
                    if (mount_ret < 0) {
                        note_sd_write_failure(mount_ret);
                        next_batch_flush_attempt_ms = now + RAW_FLUSH_INTERVAL_MS;
                    }
                }
                if (is_mounted && atomic_get(&storage_health) != SD_STORAGE_TERMINAL) {
                    (void) flush_current_batch(false);
                }
                sd_set_io_low_power(true);
            }
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
                (void) mount_for_pending_write();
            }
            if (!process_or_retain_accepted_write(&req)) {
                break;
            }
            for (int i = 0; i < WRITE_DRAIN_BURST; i++) {
                if (k_msgq_num_used_get(&sd_prio_msgq) > 0) {
                    break;
                }

                sd_req_t next_req;
                if (k_msgq_get(&sd_msgq, &next_req, K_NO_WAIT) != 0) {
                    break;
                }

                if (next_req.type == REQ_WRITE_DATA) {
                    if (!process_or_retain_accepted_write(&next_req)) {
                        break;
                    }
                }
            }
            break;

        case REQ_GET_RING_INFO:
            /* Priority commands can overtake regular write requests. Drain
             * accepted audio first so the returned snapshot includes the
             * packer tail queued at BLE connect. */
            if (req.u.info.resp) {
                int commit_res;
                if (atomic_get(&storage_health) == SD_STORAGE_TERMINAL) {
                    commit_res = drain_pending_write_queue();
                    req.u.info.resp->info = ring_info_with_terminal_losses();
                } else {
                    commit_res = commit_pending_writes_for_snapshot();
                    if (commit_res == 0) {
                        req.u.info.resp->info = ring_state;
                    }
                }
                req.u.info.resp->res = commit_res;
                k_sem_give(&req.u.info.resp->sem);
                release_resp_busy(req.u.info.resp->busy_flag);
            }
            break;

        case REQ_READ_PACKETS:
            if (req.u.read.resp) {
                int commit_res = atomic_get(&storage_health) == SD_STORAGE_TERMINAL
                                     ? drain_pending_write_queue()
                                     : commit_pending_writes_for_snapshot();
                bool terminal_read = atomic_get(&storage_health) == SD_STORAGE_TERMINAL;
                req.u.read.resp->res = commit_res < 0 ? commit_res
                                                      : read_packets_internal(req.u.read.start_seq,
                                                                              req.u.read.out_buf,
                                                                              req.u.read.max_bytes,
                                                                              &req.u.read.resp->bytes_read,
                                                                              &req.u.read.resp->packets_read,
                                                                              !terminal_read);
                k_sem_give(&req.u.read.resp->sem);
                release_resp_busy(req.u.read.resp->busy_flag);
            }
            break;

        case REQ_ADVANCE_READ:
            if (req.u.advance.resp) {
                bool terminal = atomic_get(&storage_health) == SD_STORAGE_TERMINAL;
                req.u.advance.resp->res = ring_storage_media_mutation_allowed(terminal)
                                              ? advance_read_seq_durably_internal(req.u.advance.new_read_seq)
                                              : -EROFS;
                k_sem_give(&req.u.advance.resp->sem);
                release_resp_busy(req.u.advance.resp->busy_flag);
            }
            break;

        case REQ_CLEAR_RING:
            if (req.u.status.resp) {
                bool terminal = atomic_get(&storage_health) == SD_STORAGE_TERMINAL;
                req.u.status.resp->res =
                    ring_storage_media_mutation_allowed(terminal) ? clear_ring_internal(false) : -EROFS;
                k_sem_give(&req.u.status.resp->sem);
                release_resp_busy(req.u.status.resp->busy_flag);
            }
            break;

        case REQ_FLUSH:
            res = drain_pending_write_queue();
            if (res == 0 && ring_storage_media_mutation_allowed(atomic_get(&storage_health) == SD_STORAGE_TERMINAL)) {
                res = flush_current_batch(true);
            }
            if (req.u.status.resp) {
                req.u.status.resp->res = res;
                k_sem_give(&req.u.status.resp->sem);
                release_resp_busy(req.u.status.resp->busy_flag);
            }
            break;

        case REQ_UNMOUNT:
            res = drain_pending_write_queue();
            if (res == 0) {
                res = atomic_get(&storage_health) == SD_STORAGE_TERMINAL ? deinit_mounted_media_without_flush()
                                                                         : sd_unmount();
            }
            if (req.u.status.resp) {
                req.u.status.resp->res = res;
                k_sem_give(&req.u.status.resp->sem);
                release_resp_busy(req.u.status.resp->busy_flag);
            }
            break;

        case REQ_POWER_OFF:
            /* Idle (mic asleep): flush, unmount and cut SD power to save current.
             * Drain buffered writes first (like the shutdown path) so audio queued
             * just before idle is not lost when we unmount. */
            if (atomic_get(&desired_sd_power_on)) {
                atomic_clear(&pending_idle_power_off);
                break;
            }
            if (atomic_get(&storage_health) == SD_STORAGE_TERMINAL) {
                (void) drain_pending_write_queue();
                res = deinit_mounted_media_without_flush();
                if (res == 0) {
                    res = sd_enable_power(false);
                }
                if (res < 0) {
                    atomic_set(&pending_idle_power_off, 1);
                    idle_power_off_retry_deadline_ms = k_uptime_get() + SD_POWER_OFF_RETRY_MS;
                    break;
                }
                gpio_pin_set_raw(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 11, 0);
                atomic_clear(&pending_idle_power_off);
                break;
            }
            if (is_mounted) {
                res = drain_pending_write_queue();
                if (res < 0) {
                    LOG_WRN("SD power-off deferred while accepted audio is retained: %d", res);
                    atomic_set(&pending_idle_power_off, 1);
                    idle_power_off_retry_deadline_ms = k_uptime_get() + SD_POWER_OFF_RETRY_MS;
                    break;
                }
                res = sd_unmount();
                if (res < 0) {
                    LOG_ERR("SD power-off aborted after flush/sync failure: %d", res);
                    atomic_set(&pending_idle_power_off, 1);
                    idle_power_off_retry_deadline_ms = k_uptime_get() + SD_POWER_OFF_RETRY_MS;
                    break;
                }
                /* Park the SD chip-select at physical 0 V. The SPI driver otherwise
                 * idles it HIGH, which forward-biases the unpowered card's input
                 * clamp and leaks current. Use *_raw so the driver's active-low
                 * inversion does not flip the level. Keep it an output owned by the
                 * driver (do NOT disconnect) so the card still re-inits on wake.
                 * SCK/MOSI/MISO are shared with the OTA flash on spi3, not parked. */
                gpio_pin_set_raw(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 11, 0);
                atomic_clear(&pending_idle_power_off);
                LOG_INF("SD powered off (idle, CS parked low)");
            }
            break;

        case REQ_POWER_ON:
            if (!atomic_get(&desired_sd_power_on) || sd_shutdown_in_progress) {
                atomic_clear(&pending_power_on);
                break;
            }
            if (atomic_get(&storage_health) == SD_STORAGE_TERMINAL) {
                atomic_clear(&pending_power_on);
                break;
            }
            atomic_clear(&pending_idle_power_off);
            /* Mic woke: power on + remount. Handled via the prio queue so it runs
             * before any buffered write is dequeued from sd_msgq. */
            if (!is_mounted) {
                /* CS back to inactive (physical high) before powering the card, per
                 * SD SPI power-up sequencing. */
                gpio_pin_set_raw(DEVICE_DT_GET(DT_NODELABEL(gpio1)), 11, 1);
                int mret = mount_for_pending_write();
                if (mret == 0) {
                    atomic_clear(&pending_power_on);
                    LOG_INF("SD powered on + remounted");
                } else {
                    LOG_ERR("SD remount failed: %d", mret);
                    if (ring_power_on_reconcile_required(atomic_get(&desired_sd_power_on) != 0, is_mounted, mret)) {
                        power_on_retry_deadline_ms = k_uptime_get() + SD_POWER_ON_RETRY_MS;
                        atomic_set(&pending_power_on, 1);
                    }
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
    terminal_at_risk_records = 0U;
    last_terminal_record_log_ms = 0;
    retained_write_pending = false;
    retained_write_retry_delay_ms = 0U;
    retained_write_retry_deadline_ms = 0;
    sd_write_recovery_init(&write_recovery_policy);
    write_recovery_action = SD_WRITE_RECOVERY_ACTION_RETRY;
    atomic_set(&storage_health, SD_STORAGE_HEALTHY);
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
    static struct status_resp resp;
    static atomic_t shutdown_in_flight = ATOMIC_INIT(0);

    if (!atomic_cas(&shutdown_in_flight, 0, 1)) {
        return -EBUSY;
    }

    /* Supersede any queued idle power-off; this path owns the final unmount. */
    atomic_set(&desired_sd_power_on, 1);
    atomic_clear(&pending_power_on);
    atomic_clear(&pending_idle_power_off);
    sd_shutdown_in_progress = true;
    bool unmount_completed = false;
    int shutdown_error = 0;

    if (is_mounted && sd_worker_tid) {
        k_sem_init(&resp.sem, 0, 1);
        resp.busy_flag = &shutdown_in_flight;
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
                shutdown_error = resp.res < 0 ? resp.res : -ETIMEDOUT;
            }
        } else {
            LOG_ERR("Failed to queue raw ring unmount request: %d", qret);
            shutdown_error = qret;
            resp.busy_flag = NULL;
            atomic_clear(&shutdown_in_flight);
        }
    } else {
        atomic_clear(&shutdown_in_flight);
    }

    if (is_mounted && !unmount_completed) {
        sd_shutdown_in_progress = false;
        return shutdown_error != 0 ? shutdown_error : -EIO;
    }

    if (unmount_completed || !is_mounted) {
        if (sd_enabled) {
            int power_ret = sd_enable_power(false);
            if (power_ret < 0) {
                sd_shutdown_in_progress = false;
                atomic_clear(&shutdown_in_flight);
                return power_ret;
            }
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

    atomic_clear(&shutdown_in_flight);
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

sd_storage_health_t sd_storage_health(void)
{
    return (sd_storage_health_t) atomic_get(&storage_health);
}

int sd_request_power(bool on)
{
    sd_req_t req = {0};
    req.type = on ? REQ_POWER_ON : REQ_POWER_OFF;

    /*
     * Publish intent before waking the worker. A queued stale POWER_OFF then
     * observes a newer POWER_ON and becomes a no-op instead of racing the mic
     * wake path.
     */
    atomic_set(&desired_sd_power_on, on ? 1 : 0);
    if (on) {
        atomic_clear(&pending_idle_power_off);
    } else {
        atomic_clear(&pending_power_on);
    }

    /* Queue with a timeout and check the result (like the other prio-queue
     * callers). A silently dropped REQ_POWER_ON would leave sd_enabled=true with
     * no remount -> subsequent writes lost. */
    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret != 0) {
        LOG_ERR("sd_request_power(%s) failed to queue: %d", on ? "on" : "off", ret);
        if (ring_power_on_reconcile_required(on, is_mounted, ret)) {
            power_on_retry_deadline_ms = k_uptime_get() + SD_POWER_ON_RETRY_MS;
            atomic_set(&pending_power_on, 1);
        } else if (!on) {
            atomic_set(&pending_idle_power_off, 1);
        }
        return ret;
    }

    if (on) {
        atomic_clear(&pending_power_on);
        /* Only after the POWER_ON is queued: mark SD available so the audio
         * pusher keeps writing; the writes buffer in sd_msgq until the remount
         * (prio request) completes. */
        sd_enabled = true;
    }
    return 0;
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

uint32_t write_to_file(const uint8_t *data, uint32_t length)
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

    if (sd_shutdown_in_progress) {
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
            LOG_ERR("write_to_file rejected: SD write path is terminal");
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
    req.u.write.timestamp = ring_record_timestamp_or_zero(rtc_is_valid(), get_utc_time());

    int ret = k_msgq_put(&sd_msgq, &req, K_NO_WAIT);
    if (ret != 0) {
        ret = k_msgq_put(&sd_msgq, &req, ble_connected ? K_MSEC(1) : K_MSEC(5));
    }

    if (ret != 0) {
        write_rejected_records++;
        int64_t now = k_uptime_get();
        if (now - last_write_err_log_ms > 2000) {
            LOG_WRN("Write queue full, record rejected for ordered retry (%d), rejected attempts=%u",
                    ret,
                    write_rejected_records);
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

int sd_ring_advance(uint64_t new_read_seq)
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
    req.u.advance.resp = &resp;

    int ret = k_msgq_put(&sd_prio_msgq, &req, K_MSEC(500));
    if (ret != 0) {
        resp.busy_flag = NULL;
        atomic_clear(&advance_in_flight);
        return ret;
    }

    ret = wait_for_sd_worker_response(&resp.sem, 5000, "sd_ring_advance");
    if (ret < 0) {
        return ret;
    }

    return resp.res;
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
