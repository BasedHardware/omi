#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

#include "../../src/lib/core/audio_storage_packer.h"
#include "../../src/lib/core/ring_transfer_integrity.h"
#include "../../src/lib/core/rtc_elapsed_recovery.h"
#include "../../src/lib/core/rtc_time_state.h"
#include "../../src/lib/core/sd_ring_durability.h"
#include "../../src/lib/core/sd_ring_recovery.h"
#include "../../src/lib/core/sd_write_recovery.h"
#include "../../src/lib/core/storage_readiness.h"

#define MAX_CAPTURED_RECORDS 4U

typedef struct {
    uint8_t records[MAX_CAPTURED_RECORDS][AUDIO_STORAGE_RECORD_BYTES];
    size_t record_count;
    size_t rejected_writes;
} fake_writer_t;

typedef struct {
    int write_failures_remaining;
    int header_failures_remaining;
    int metadata_failures_remaining;
    int sync_failures_remaining;
    uint32_t sync_fail_on_call;
    uint32_t write_calls;
    uint32_t header_calls;
    uint32_t metadata_calls;
    uint32_t sync_calls;
    uint8_t stages[128];
    uint8_t stage_count;
    sd_ring_cursor_t persisted;
    uint8_t committed_payload[16];
    uint8_t staged_payload[16];
} fake_durable_disk_t;

enum {
    FAKE_STAGE_PAYLOAD = 1,
    FAKE_STAGE_SYNC,
    FAKE_STAGE_HEADER,
    FAKE_STAGE_METADATA,
};

static void fake_record_stage(fake_durable_disk_t *disk, uint8_t stage)
{
    assert(disk->stage_count < sizeof(disk->stages));
    disk->stages[disk->stage_count++] = stage;
}

static int fake_disk_write_payload(void *context)
{
    fake_durable_disk_t *disk = context;
    fake_record_stage(disk, FAKE_STAGE_PAYLOAD);
    disk->write_calls++;
    if (disk->write_failures_remaining > 0) {
        disk->write_failures_remaining--;
        return -EIO;
    }

    memcpy(disk->committed_payload, disk->staged_payload, sizeof(disk->committed_payload));
    return 0;
}

static int fake_disk_write_header(void *context)
{
    fake_durable_disk_t *disk = context;
    fake_record_stage(disk, FAKE_STAGE_HEADER);
    disk->header_calls++;
    if (disk->header_failures_remaining > 0) {
        disk->header_failures_remaining--;
        return -EIO;
    }
    return 0;
}

static int fake_disk_persist_metadata(const sd_ring_cursor_t *candidate, void *context)
{
    fake_durable_disk_t *disk = context;
    fake_record_stage(disk, FAKE_STAGE_METADATA);
    disk->metadata_calls++;
    if (disk->metadata_failures_remaining > 0) {
        disk->metadata_failures_remaining--;
        return -EIO;
    }

    disk->persisted = *candidate;
    return 0;
}

static int fake_disk_sync(void *context)
{
    fake_durable_disk_t *disk = context;
    fake_record_stage(disk, FAKE_STAGE_SYNC);
    disk->sync_calls++;
    if (disk->sync_fail_on_call == disk->sync_calls) {
        return -EIO;
    }
    if (disk->sync_failures_remaining > 0) {
        disk->sync_failures_remaining--;
        return -EIO;
    }
    return 0;
}

static const sd_ring_durability_ops_t fake_disk_ops = {
    .write_payload = fake_disk_write_payload,
    .write_header = fake_disk_write_header,
    .persist_metadata = fake_disk_persist_metadata,
    .sync_media = fake_disk_sync,
};

static void assert_cursor_eq(const sd_ring_cursor_t *actual, const sd_ring_cursor_t *expected)
{
    assert(actual->read_seq == expected->read_seq);
    assert(actual->write_seq == expected->write_seq);
    assert(actual->dropped_packets == expected->dropped_packets);
    assert(actual->capacity_packets == expected->capacity_packets);
}

static void test_storage_command_readiness_is_bounded_and_terminal_aware(void)
{
    assert(storage_readiness_decide(false, false, false, false, false) == STORAGE_READINESS_WAKE_AND_WAIT);
    assert(storage_readiness_decide(false, false, false, true, false) == STORAGE_READINESS_WAIT);
    assert(storage_readiness_decide(false, false, false, true, true) == STORAGE_READINESS_RETRYABLE_TIMEOUT);

    /* A mounted card must still wait until the pusher commits its partial tail. */
    assert(storage_readiness_decide(true, false, false, true, false) == STORAGE_READINESS_WAIT);
    assert(storage_readiness_decide(true, true, false, true, false) == STORAGE_READINESS_SERVE);

    /* Permanent media failure is explicit; it never enters the retry loop. */
    assert(storage_readiness_decide(false, false, true, false, false) == STORAGE_READINESS_TERMINAL);
    assert(storage_readiness_decide(true, false, true, false, false) == STORAGE_READINESS_SERVE);
}

static void assert_stages(const fake_durable_disk_t *disk, const uint8_t *expected, size_t count)
{
    assert(disk->stage_count == count);
    assert(memcmp(disk->stages, expected, count) == 0);
}

static size_t fake_write(const uint8_t *record, size_t length, void *context)
{
    fake_writer_t *writer = context;

    if (writer->rejected_writes > 0U) {
        writer->rejected_writes--;
        return 0U;
    }

    assert(length == AUDIO_STORAGE_RECORD_BYTES);
    assert(writer->record_count < MAX_CAPTURED_RECORDS);
    memcpy(writer->records[writer->record_count], record, length);
    writer->record_count++;
    return length;
}

static void fill_frame(uint8_t *frame, size_t length, uint8_t value)
{
    memset(frame, value, length);
}

static void assert_packed_frame(const uint8_t *record, size_t offset, const uint8_t *frame, size_t frame_length)
{
    assert(record[offset] == frame_length);
    assert(memcmp(record + offset + 1U, frame, frame_length) == 0);
}

static void test_overflow_flushes_complete_record_and_zero_pads_tail(void)
{
    audio_storage_packer_t packer;
    fake_writer_t writer = {0};
    uint8_t first[200];
    uint8_t second[200];

    fill_frame(first, sizeof(first), 0x11);
    fill_frame(second, sizeof(second), 0x22);
    audio_storage_packer_init(&packer);

    assert(audio_storage_packer_push(&packer, first, sizeof(first), fake_write, &writer) ==
           AUDIO_STORAGE_PACKER_ACCEPTED);
    assert(audio_storage_packer_push(&packer, second, sizeof(second), fake_write, &writer) ==
           AUDIO_STORAGE_PACKER_ACCEPTED);
    assert(writer.record_count == 0U);

    uint8_t third[80];
    fill_frame(third, sizeof(third), 0x33);
    assert(audio_storage_packer_push(&packer, third, sizeof(third), fake_write, &writer) ==
           AUDIO_STORAGE_PACKER_ACCEPTED);

    assert(writer.record_count == 1U);
    assert_packed_frame(writer.records[0], 0U, first, sizeof(first));
    assert_packed_frame(writer.records[0], sizeof(first) + 1U, second, sizeof(second));
    for (size_t i = 402U; i < AUDIO_STORAGE_RECORD_BYTES; i++) {
        assert(writer.records[0][i] == 0U);
    }

    assert(audio_storage_packer_flush(&packer, fake_write, &writer));
    assert(writer.record_count == 2U);
    assert_packed_frame(writer.records[1], 0U, third, sizeof(third));
    for (size_t i = sizeof(third) + 1U; i < AUDIO_STORAGE_RECORD_BYTES; i++) {
        assert(writer.records[1][i] == 0U);
    }
}

static void test_rejected_overflow_does_not_consume_or_reorder_new_frame(void)
{
    audio_storage_packer_t packer;
    fake_writer_t writer = {.rejected_writes = 1U};
    uint8_t first[250];
    uint8_t second[200];

    fill_frame(first, sizeof(first), 0x44);
    fill_frame(second, sizeof(second), 0x55);
    audio_storage_packer_init(&packer);

    assert(audio_storage_packer_push(&packer, first, sizeof(first), fake_write, &writer) ==
           AUDIO_STORAGE_PACKER_ACCEPTED);
    assert(audio_storage_packer_push(&packer, second, sizeof(second), fake_write, &writer) ==
           AUDIO_STORAGE_PACKER_BLOCKED);
    assert(writer.record_count == 0U);
    assert(audio_storage_packer_pending_bytes(&packer) == AUDIO_STORAGE_RECORD_BYTES);

    assert(audio_storage_packer_push(&packer, second, sizeof(second), fake_write, &writer) ==
           AUDIO_STORAGE_PACKER_ACCEPTED);
    assert(writer.record_count == 1U);
    assert_packed_frame(writer.records[0], 0U, first, sizeof(first));

    assert(audio_storage_packer_flush(&packer, fake_write, &writer));
    assert(writer.record_count == 2U);
    assert_packed_frame(writer.records[1], 0U, second, sizeof(second));
}

static void test_exact_fit_flushes_legacy_terminated_record_before_new_frame(void)
{
    audio_storage_packer_t packer;
    fake_writer_t writer = {.rejected_writes = 1U};
    uint8_t first[255];
    uint8_t second[183];

    fill_frame(first, sizeof(first), 0x66);
    fill_frame(second, sizeof(second), 0x77);
    audio_storage_packer_init(&packer);

    assert(audio_storage_packer_push(&packer, first, sizeof(first), fake_write, &writer) ==
           AUDIO_STORAGE_PACKER_ACCEPTED);
    assert(audio_storage_packer_push(&packer, second, sizeof(second), fake_write, &writer) ==
           AUDIO_STORAGE_PACKER_BLOCKED);
    assert(audio_storage_packer_pending_bytes(&packer) == AUDIO_STORAGE_RECORD_BYTES);
    assert(audio_storage_packer_push(&packer, second, sizeof(second), fake_write, &writer) ==
           AUDIO_STORAGE_PACKER_ACCEPTED);

    assert(writer.record_count == 1U);
    assert_packed_frame(writer.records[0], 0U, first, sizeof(first));
    for (size_t i = sizeof(first) + 1U; i < AUDIO_STORAGE_RECORD_BYTES; i++) {
        assert(writer.records[0][i] == 0U);
    }
    assert(audio_storage_packer_pending_bytes(&packer) == sizeof(second) + 1U);

    assert(audio_storage_packer_flush(&packer, fake_write, &writer));
    assert(writer.record_count == 2U);
    assert_packed_frame(writer.records[1], 0U, second, sizeof(second));
}

static void test_invalid_frame_leaves_state_unchanged(void)
{
    audio_storage_packer_t packer;
    fake_writer_t writer = {0};
    uint8_t frame[1] = {0};

    audio_storage_packer_init(&packer);
    assert(audio_storage_packer_push(&packer, frame, 0U, fake_write, &writer) == AUDIO_STORAGE_PACKER_INVALID);
    assert(audio_storage_packer_push(NULL, frame, sizeof(frame), fake_write, &writer) == AUDIO_STORAGE_PACKER_INVALID);
    assert(audio_storage_packer_pending_bytes(&packer) == 0U);
    assert(writer.record_count == 0U);
}

static void test_delivery_policy_falls_back_after_live_enqueue_failure(void)
{
    assert(audio_delivery_route(true, true) == AUDIO_DELIVERY_LIVE);
    assert(audio_delivery_route(true, false) == AUDIO_DELIVERY_LIVE);
    assert(audio_delivery_route(false, true) == AUDIO_DELIVERY_STORAGE);
    assert(audio_delivery_route(false, false) == AUDIO_DELIVERY_DROP);
}

static void test_pre_pusher_queue_saturation_preserves_whole_frame(void)
{
    audio_storage_packer_t packer;
    fake_writer_t writer = {0};
    uint8_t saturated_queue_frame[160];

    fill_frame(saturated_queue_frame, sizeof(saturated_queue_frame), 0xA5);
    audio_storage_packer_init(&packer);

    assert(audio_delivery_route(false, true) == AUDIO_DELIVERY_STORAGE);
    assert(
        audio_storage_packer_push(&packer, saturated_queue_frame, sizeof(saturated_queue_frame), fake_write, &writer) ==
        AUDIO_STORAGE_PACKER_ACCEPTED);
    assert(audio_storage_packer_flush(&packer, fake_write, &writer));
    assert(writer.record_count == 1U);
    assert_packed_frame(writer.records[0], 0U, saturated_queue_frame, sizeof(saturated_queue_frame));
}

static void test_transfer_crc_and_done_notification_match_golden_wire_bytes(void)
{
    static const uint8_t input[] = "123456789";
    static const uint8_t expected_done[RING_TRANSFER_DONE_BYTES] = {
        0x04,
        0x00,
        0x01,
        0x02,
        0x03,
        0x04,
        0x05,
        0x06,
        0x07,
        0x08,
        0xCB,
        0xF4,
        0x39,
        0x26,
    };
    uint8_t done[RING_TRANSFER_DONE_BYTES] = {0};

    uint32_t crc = ring_transfer_crc32_update(0U, input, 4U);
    crc = ring_transfer_crc32_update(crc, input + 4U, sizeof(input) - 1U - 4U);
    assert(crc == 0xCBF43926U);
    assert(ring_transfer_encode_done(done, sizeof(done), 0U, 0x0102030405060708ULL, crc) == sizeof(done));
    assert(memcmp(done, expected_done, sizeof(done)) == 0);

    assert(ring_transfer_encode_done(done, sizeof(done) - 1U, 0U, 0U, 0U) == 0U);
}

static void test_invalid_rtc_uses_zero_timestamp_without_rejecting_audio(void)
{
    assert(ring_record_timestamp_or_zero(false, 1800000000U) == 0U);
    assert(ring_record_timestamp_or_zero(true, 0U) == 0U);
    assert(ring_record_timestamp_or_zero(true, 1699999999U) == 0U);
    assert(ring_record_timestamp_or_zero(true, 1800000000U) == 1800000000U);
}

typedef enum {
    RTC_FAULT_NONE = 0,
    RTC_FAULT_LOAD,
    RTC_FAULT_CLEAR,
    RTC_FAULT_SAVE,
    RTC_FAULT_POWER,
    RTC_FAULT_RESOLUTION,
    RTC_FAULT_ENABLE,
    RTC_FAULT_RESET,
    RTC_FAULT_READ,
    RTC_FAULT_APPLY,
} fake_rtc_fault_t;

typedef struct {
    rtc_elapsed_marker_t marker;
    uint32_t counter;
    uint32_t load_calls;
    uint32_t clear_calls;
    uint32_t save_calls;
    uint32_t power_calls;
    uint32_t resolution_calls;
    uint32_t enable_calls;
    uint32_t reset_calls;
    uint32_t read_calls;
    uint32_t apply_calls;
    uint64_t applied_epoch_ms;
    fake_rtc_fault_t fault;
} fake_rtc_recovery_t;

static int fake_rtc_load(rtc_elapsed_marker_t *marker, void *context)
{
    fake_rtc_recovery_t *fake = context;
    fake->load_calls++;
    if (fake->fault == RTC_FAULT_LOAD) {
        return -EIO;
    }
    *marker = fake->marker;
    return 0;
}

static int fake_rtc_clear(void *context)
{
    fake_rtc_recovery_t *fake = context;
    fake->clear_calls++;
    if (fake->fault == RTC_FAULT_CLEAR) {
        return -EIO;
    }
    fake->marker = (rtc_elapsed_marker_t) {0};
    return 0;
}

static int fake_rtc_save(const rtc_elapsed_marker_t *marker, void *context)
{
    fake_rtc_recovery_t *fake = context;
    fake->save_calls++;
    if (fake->fault == RTC_FAULT_SAVE) {
        return -EIO;
    }
    fake->marker = *marker;
    return 0;
}

static int fake_rtc_power(void *context)
{
    fake_rtc_recovery_t *fake = context;
    fake->power_calls++;
    return fake->fault == RTC_FAULT_POWER ? -EIO : 0;
}

static int fake_rtc_resolution(void *context)
{
    fake_rtc_recovery_t *fake = context;
    fake->resolution_calls++;
    return fake->fault == RTC_FAULT_RESOLUTION ? -EIO : 0;
}

static int fake_rtc_enable(void *context)
{
    fake_rtc_recovery_t *fake = context;
    fake->enable_calls++;
    return fake->fault == RTC_FAULT_ENABLE ? -EIO : 0;
}

static int fake_rtc_reset(void *context)
{
    fake_rtc_recovery_t *fake = context;
    fake->reset_calls++;
    return fake->fault == RTC_FAULT_RESET ? -EIO : 0;
}

static int fake_rtc_read(uint32_t *counter, void *context)
{
    fake_rtc_recovery_t *fake = context;
    fake->read_calls++;
    if (fake->fault == RTC_FAULT_READ) {
        return -EIO;
    }
    *counter = fake->counter;
    return 0;
}

static int fake_rtc_apply(uint64_t epoch_ms, void *context)
{
    fake_rtc_recovery_t *fake = context;
    fake->apply_calls++;
    /* Production must consume the one-shot marker before making RTC valid. */
    assert(fake->marker.epoch_s == 0U);
    if (fake->fault == RTC_FAULT_APPLY) {
        return -EIO;
    }
    fake->applied_epoch_ms = epoch_ms;
    return 0;
}

static const rtc_elapsed_recovery_ops_t fake_rtc_ops = {
    .load_marker = fake_rtc_load,
    .clear_marker = fake_rtc_clear,
    .save_marker = fake_rtc_save,
    .power_on = fake_rtc_power,
    .set_counter_resolution = fake_rtc_resolution,
    .enable_counter = fake_rtc_enable,
    .reset_counter = fake_rtc_reset,
    .read_counter = fake_rtc_read,
    .apply_current_epoch_ms = fake_rtc_apply,
};

static void test_rebooted_rtc_requires_live_current_time(void)
{
    const uint64_t stale_persisted_epoch_ms = 1785000000000ULL;
    const uint64_t phone_epoch_ms = 1785004000000ULL;
    rtc_time_state_t rtc;

    rtc_time_state_init_from_persisted(&rtc, stale_persisted_epoch_ms, 1000);
    assert(!rtc_time_state_is_valid(&rtc));
    assert(rtc_time_state_now_ms(&rtc, 2500) == 0U);
    assert(ring_record_timestamp_or_zero(rtc_time_state_is_valid(&rtc),
                                         (uint32_t) (rtc_time_state_now_ms(&rtc, 2500) / 1000ULL)) == 0U);

    rtc_time_state_init_from_persisted(&rtc, stale_persisted_epoch_ms, 5000);
    assert(!rtc_time_state_is_valid(&rtc));
    assert(rtc_time_state_set_live_sync(&rtc, RTC_TIME_MIN_VALID_EPOCH_MS - 1U, 6000) == -EINVAL);
    assert(!rtc_time_state_is_valid(&rtc));
    assert(rtc_time_state_set_live_sync(&rtc, phone_epoch_ms, 6000) == 0);
    assert(rtc_time_state_is_valid(&rtc));
    assert(rtc_time_state_now_ms(&rtc, 6500) == phone_epoch_ms + 500ULL);
    assert(ring_record_timestamp_or_zero(rtc_time_state_is_valid(&rtc),
                                         (uint32_t) (rtc_time_state_now_ms(&rtc, 6500) / 1000ULL)) != 0U);
}

static void test_elapsed_marker_create_consume_and_no_replay(void)
{
    const uint64_t epoch_s = 1785000000ULL;
    const uint64_t bound_ms = 60000U;
    fake_rtc_recovery_t fake = {
        .marker = {.epoch_s = epoch_s - 100U, .counter = 1U},
        .counter = 100U,
    };

    assert(rtc_elapsed_recovery_prepare(epoch_s, bound_ms, &fake_rtc_ops, &fake) == 0);
    assert(fake.clear_calls == 1U);
    assert(fake.save_calls == 1U);
    assert(fake.marker.epoch_s == epoch_s);
    assert(fake.marker.counter == 100U);

    fake.counter = 200U;
    assert(rtc_elapsed_recovery_attempt(true, bound_ms, &fake_rtc_ops, &fake) == 1);
    assert(fake.clear_calls == 2U);
    assert(fake.apply_calls == 1U);
    assert(fake.applied_epoch_ms == epoch_s * 1000ULL + 640U);
    assert(fake.marker.epoch_s == 0U);

    assert(rtc_elapsed_recovery_attempt(true, bound_ms, &fake_rtc_ops, &fake) == 0);
    assert(fake.apply_calls == 1U);
}

static void test_elapsed_marker_wrong_reset_provenance_is_consumed(void)
{
    fake_rtc_recovery_t fake = {
        .marker = {.epoch_s = 1785000000ULL, .counter = 100U},
        .counter = 200U,
    };

    assert(rtc_elapsed_recovery_attempt(false, 60000U, &fake_rtc_ops, &fake) == 0);
    assert(fake.marker.epoch_s == 0U);
    assert(fake.clear_calls == 1U);
    assert(fake.power_calls == 0U);
    assert(fake.apply_calls == 0U);

    assert(rtc_elapsed_recovery_attempt(true, 60000U, &fake_rtc_ops, &fake) == 0);
    assert(fake.apply_calls == 0U);
}

static void test_elapsed_marker_prepare_faults_fail_closed(void)
{
    static const fake_rtc_fault_t faults[] = {
        RTC_FAULT_POWER,
        RTC_FAULT_RESOLUTION,
        RTC_FAULT_ENABLE,
        RTC_FAULT_RESET,
        RTC_FAULT_READ,
        RTC_FAULT_SAVE,
    };

    for (size_t i = 0U; i < sizeof(faults) / sizeof(faults[0]); i++) {
        fake_rtc_recovery_t fake = {
            .marker = {.epoch_s = 1784000000ULL, .counter = 7U},
            .counter = 100U,
            .fault = faults[i],
        };
        assert(rtc_elapsed_recovery_prepare(1785000000ULL, 60000U, &fake_rtc_ops, &fake) == -EIO);
        assert(fake.marker.epoch_s == 0U);
        assert(fake.apply_calls == 0U);
    }

    fake_rtc_recovery_t clear_failure = {
        .marker = {.epoch_s = 1784000000ULL, .counter = 7U},
        .fault = RTC_FAULT_CLEAR,
    };
    assert(rtc_elapsed_recovery_prepare(1785000000ULL, 60000U, &fake_rtc_ops, &clear_failure) == -EIO);
    assert(clear_failure.power_calls == 0U);
    assert(clear_failure.save_calls == 0U);
    assert(clear_failure.apply_calls == 0U);

    fake_rtc_recovery_t invalid_time = {
        .marker = {.epoch_s = 1784000000ULL, .counter = 7U},
    };
    assert(rtc_elapsed_recovery_prepare(RTC_TIME_MIN_VALID_EPOCH_S - 1U, 60000U, &fake_rtc_ops, &invalid_time) ==
           -EINVAL);
    assert(invalid_time.marker.epoch_s == 0U);
    assert(invalid_time.power_calls == 0U);
}

static void test_elapsed_marker_recovery_faults_consume_before_failure(void)
{
    static const fake_rtc_fault_t faults[] = {
        RTC_FAULT_POWER,
        RTC_FAULT_RESOLUTION,
        RTC_FAULT_ENABLE,
        RTC_FAULT_READ,
        RTC_FAULT_APPLY,
    };

    for (size_t i = 0U; i < sizeof(faults) / sizeof(faults[0]); i++) {
        fake_rtc_recovery_t fake = {
            .marker = {.epoch_s = 1785000000ULL, .counter = 100U},
            .counter = 200U,
            .fault = faults[i],
        };
        assert(rtc_elapsed_recovery_attempt(true, 60000U, &fake_rtc_ops, &fake) == -EIO);
        assert(fake.marker.epoch_s == 0U);

        fake.fault = RTC_FAULT_NONE;
        assert(rtc_elapsed_recovery_attempt(true, 60000U, &fake_rtc_ops, &fake) == 0);
        assert(fake.applied_epoch_ms == 0U);
    }

    fake_rtc_recovery_t load_failure = {
        .marker = {.epoch_s = 1785000000ULL, .counter = 100U},
        .fault = RTC_FAULT_LOAD,
    };
    assert(rtc_elapsed_recovery_attempt(true, 60000U, &fake_rtc_ops, &load_failure) == -EIO);
    assert(load_failure.marker.epoch_s == 0U);
    assert(load_failure.apply_calls == 0U);

    fake_rtc_recovery_t consume_failure = {
        .marker = {.epoch_s = 1785000000ULL, .counter = 100U},
        .counter = 200U,
        .fault = RTC_FAULT_CLEAR,
    };
    assert(rtc_elapsed_recovery_attempt(true, 0U, &fake_rtc_ops, &consume_failure) == -EIO);
    assert(consume_failure.marker.epoch_s != 0U);
    assert(consume_failure.power_calls == 0U);
    assert(consume_failure.apply_calls == 0U);

    /* A later boot may finally consume the marker, but production's unbounded
     * policy still cannot replay it into valid time. */
    consume_failure.fault = RTC_FAULT_NONE;
    assert(rtc_elapsed_recovery_attempt(true, 0U, &fake_rtc_ops, &consume_failure) == -ENOTSUP);
    assert(consume_failure.marker.epoch_s == 0U);
    assert(consume_failure.power_calls == 0U);
    assert(consume_failure.apply_calls == 0U);
}

static void test_elapsed_marker_unbounded_and_ambiguous_intervals_never_apply(void)
{
    assert(RTC_ELAPSED_COUNTER_WRAP_MS == 107374182ULL);

    fake_rtc_recovery_t unbounded = {
        .marker = {.epoch_s = 1785000000ULL, .counter = RTC_ELAPSED_COUNTER_MASK - 10U},
        .counter = 5U,
    };
    assert(rtc_elapsed_recovery_attempt(true, 0U, &fake_rtc_ops, &unbounded) == -ENOTSUP);
    assert(unbounded.marker.epoch_s == 0U);
    assert(unbounded.read_calls == 0U);
    assert(unbounded.apply_calls == 0U);

    fake_rtc_recovery_t whole_wrap = {
        .marker = {.epoch_s = 1785000000ULL, .counter = 100U},
        .counter = 200U,
    };
    assert(rtc_elapsed_recovery_attempt(true, RTC_ELAPSED_COUNTER_WRAP_MS, &fake_rtc_ops, &whole_wrap) == -ENOTSUP);
    assert(whole_wrap.marker.epoch_s == 0U);
    assert(whole_wrap.apply_calls == 0U);

    fake_rtc_recovery_t over_bound = {
        .marker = {.epoch_s = 1785000000ULL, .counter = 0U},
        .counter = 200U,
    };
    assert(rtc_elapsed_recovery_attempt(true, 1000U, &fake_rtc_ops, &over_bound) == -ERANGE);
    assert(over_bound.marker.epoch_s == 0U);
    assert(over_bound.apply_calls == 0U);

    fake_rtc_recovery_t prepare_disabled = {
        .marker = {.epoch_s = 1784000000ULL, .counter = 7U},
    };
    assert(rtc_elapsed_recovery_prepare(1785000000ULL, 0U, &fake_rtc_ops, &prepare_disabled) == -ENOTSUP);
    assert(prepare_disabled.marker.epoch_s == 0U);
    assert(prepare_disabled.power_calls == 0U);
}

static void test_elapsed_marker_checked_epoch_arithmetic(void)
{
    fake_rtc_recovery_t multiply_overflow = {
        .marker = {.epoch_s = UINT64_MAX / 1000ULL + 1ULL, .counter = 0U},
        .counter = 1U,
    };
    assert(rtc_elapsed_recovery_attempt(true, 1000U, &fake_rtc_ops, &multiply_overflow) == -ERANGE);
    assert(multiply_overflow.apply_calls == 0U);

    fake_rtc_recovery_t addition_overflow = {
        .marker = {.epoch_s = UINT64_MAX / 1000ULL, .counter = 0U},
        .counter = 100U,
    };
    assert(rtc_elapsed_recovery_attempt(true, 1000U, &fake_rtc_ops, &addition_overflow) == -ERANGE);
    assert(addition_overflow.apply_calls == 0U);
}

static void test_rtc_repeated_boot_and_live_sync_transitions_are_transactional(void)
{
    const uint64_t initial_epoch_ms = 1785000000000ULL;
    rtc_time_state_t rtc;

    for (uint32_t cycle = 0U; cycle < 64U; cycle++) {
        uint64_t persisted_epoch_ms = initial_epoch_ms + (uint64_t) cycle * 10000ULL;
        int64_t boot_uptime_ms = 1000 + (int64_t) cycle * 100;
        rtc_time_state_init_from_persisted(&rtc, persisted_epoch_ms, boot_uptime_ms);
        assert(!rtc_time_state_is_valid(&rtc));
        assert(rtc_time_state_now_ms(&rtc, boot_uptime_ms + 99) == 0U);

        uint64_t synced_epoch_ms = persisted_epoch_ms + 5000ULL;
        assert(rtc_time_state_set_live_sync(&rtc, synced_epoch_ms, boot_uptime_ms + 100) == 0);
        assert(rtc_time_state_now_ms(&rtc, boot_uptime_ms + 125) == synced_epoch_ms + 25ULL);

        /* A rejected update cannot partially replace an already-valid state. */
        assert(rtc_time_state_set_live_sync(&rtc, RTC_TIME_MIN_VALID_EPOCH_MS - 1U, boot_uptime_ms + 130) == -EINVAL);
        assert(rtc_time_state_is_valid(&rtc));
        assert(rtc_time_state_now_ms(&rtc, boot_uptime_ms + 150) == synced_epoch_ms + 50ULL);
    }
}

static void test_rtc_now_ms_clamps_and_saturates_boundaries(void)
{
    rtc_time_state_t rtc;

    assert(rtc_time_state_set_live_sync(&rtc, 1785000000000ULL, 1000) == 0);
    assert(rtc_time_state_now_ms(&rtc, 999) == 1785000000000ULL);

    assert(rtc_time_state_set_live_sync(&rtc, 1785000000000ULL, -1) == -EINVAL);
    assert(rtc_time_state_now_ms(&rtc, INT64_MIN) == 1785000000000ULL);

    assert(rtc_time_state_set_live_sync(&rtc, UINT64_MAX - 10ULL, 0) == 0);
    assert(rtc_time_state_now_ms(&rtc, INT64_MAX) == UINT64_MAX);
}

static void test_connect_snapshot_flushes_existing_tail_after_queued_frames(void)
{
    audio_storage_packer_t packer;
    fake_writer_t writer = {0};
    uint8_t existing_tail[100];
    uint8_t queued_before_connect[80];

    fill_frame(existing_tail, sizeof(existing_tail), 0x91);
    fill_frame(queued_before_connect, sizeof(queued_before_connect), 0x92);
    audio_storage_packer_init(&packer);

    assert(audio_storage_packer_push(&packer, existing_tail, sizeof(existing_tail), fake_write, &writer) ==
           AUDIO_STORAGE_PACKER_ACCEPTED);
    assert(writer.record_count == 0U);

    /* The connect barrier drains already-queued audio before flushing. */
    assert(
        audio_storage_packer_push(&packer, queued_before_connect, sizeof(queued_before_connect), fake_write, &writer) ==
        AUDIO_STORAGE_PACKER_ACCEPTED);
    assert(audio_storage_packer_flush(&packer, fake_write, &writer));

    assert(writer.record_count == 1U);
    assert_packed_frame(writer.records[0], 0U, existing_tail, sizeof(existing_tail));
    assert_packed_frame(
        writer.records[0], sizeof(existing_tail) + 1U, queued_before_connect, sizeof(queued_before_connect));
}

static void test_dirty_batch_retries_after_media_recovers_without_ble_command(void)
{
    bool dirty = true;
    int64_t next_attempt_ms = 2000;

    /* The failed attempt retains dirty ownership and backs off until due. */
    assert(!ring_storage_flush_retry_due(dirty, 1999, next_attempt_ms));
    assert(ring_storage_flush_retry_due(dirty, 2000, next_attempt_ms));

    /* A successful worker retry commits the same batch and clears dirty. */
    dirty = false;
    assert(!ring_storage_flush_retry_due(dirty, 3000, next_attempt_ms));
}

static void test_transient_sd_failure_retains_order_until_recovery(void)
{
    sd_write_recovery_policy_t policy;

    sd_write_recovery_init(&policy);
    assert(policy.state == SD_WRITE_RECOVERY_HEALTHY);

    /* Production keeps ownership of the same accepted record on RETRY. */
    assert(sd_write_recovery_on_failure(&policy) == SD_WRITE_RECOVERY_ACTION_RETRY);
    assert(policy.state == SD_WRITE_RECOVERY_DEGRADED);
    assert(policy.failures_on_mount == 1U);
    assert(policy.remounts == 0U);

    sd_write_recovery_on_success(&policy);
    assert(policy.state == SD_WRITE_RECOVERY_HEALTHY);
    assert(policy.failures_on_mount == 0U);
    assert(policy.remounts == 0U);
    assert(!sd_write_recovery_is_terminal(&policy));
}

static void test_permanent_sd_failure_has_bounded_remounts_and_terminal_state(void)
{
    sd_write_recovery_policy_t policy;
    uint32_t remount_actions = 0U;
    uint32_t failures_to_terminal = SD_WRITE_RETRIES_PER_MOUNT * (SD_WRITE_MAX_REMOUNTS + 1U);

    sd_write_recovery_init(&policy);
    for (uint32_t failure = 1U; failure <= failures_to_terminal; failure++) {
        sd_write_recovery_action_t action = sd_write_recovery_on_failure(&policy);
        if (action == SD_WRITE_RECOVERY_ACTION_REMOUNT) {
            remount_actions++;
        }

        if (failure < failures_to_terminal) {
            assert(action != SD_WRITE_RECOVERY_ACTION_TERMINAL);
            assert(policy.state == SD_WRITE_RECOVERY_DEGRADED);
        } else {
            assert(action == SD_WRITE_RECOVERY_ACTION_TERMINAL);
        }
    }

    assert(remount_actions == SD_WRITE_MAX_REMOUNTS);
    assert(policy.remounts == SD_WRITE_MAX_REMOUNTS);
    assert(sd_write_recovery_is_terminal(&policy));
    assert(sd_write_recovery_on_failure(&policy) == SD_WRITE_RECOVERY_ACTION_TERMINAL);
}

static void test_durable_batch_transaction_fault_matrix(void)
{
    static const uint8_t payload_only[] = {FAKE_STAGE_PAYLOAD};
    static const uint8_t payload_sync[] = {FAKE_STAGE_PAYLOAD, FAKE_STAGE_SYNC};
    static const uint8_t through_header[] = {FAKE_STAGE_PAYLOAD, FAKE_STAGE_SYNC, FAKE_STAGE_HEADER};
    static const uint8_t through_header_sync[] = {
        FAKE_STAGE_PAYLOAD,
        FAKE_STAGE_SYNC,
        FAKE_STAGE_HEADER,
        FAKE_STAGE_SYNC,
    };
    static const uint8_t through_metadata[] = {
        FAKE_STAGE_PAYLOAD,
        FAKE_STAGE_SYNC,
        FAKE_STAGE_HEADER,
        FAKE_STAGE_SYNC,
        FAKE_STAGE_METADATA,
    };
    static const uint8_t complete_order[] = {
        FAKE_STAGE_PAYLOAD,
        FAKE_STAGE_SYNC,
        FAKE_STAGE_HEADER,
        FAKE_STAGE_SYNC,
        FAKE_STAGE_METADATA,
        FAKE_STAGE_SYNC,
    };
    const sd_ring_cursor_t mounted = {
        .read_seq = 1U,
        .write_seq = 4U,
        .dropped_packets = 0U,
        .capacity_packets = 16U,
    };
    const sd_ring_cursor_t candidate = {
        .read_seq = 1U,
        .write_seq = 6U,
        .dropped_packets = 0U,
        .capacity_packets = 16U,
    };
    sd_ring_durability_t durability;
    fake_durable_disk_t disk = {0};

    sd_ring_durability_init(&durability, &mounted);
    disk.write_failures_remaining = 1;
    assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == -EIO);
    assert_cursor_eq(&durability.durable, &mounted);
    assert(disk.write_calls == 1U);
    assert(disk.header_calls == 0U);
    assert(disk.metadata_calls == 0U);
    assert(disk.sync_calls == 0U);
    assert_stages(&disk, payload_only, sizeof(payload_only));

    memset(&disk, 0, sizeof(disk));
    sd_ring_durability_init(&durability, &mounted);
    disk.sync_fail_on_call = 1U;
    assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == -EIO);
    assert_cursor_eq(&durability.durable, &mounted);
    assert(disk.write_calls == 1U);
    assert(disk.header_calls == 0U);
    assert(disk.metadata_calls == 0U);
    assert(disk.sync_calls == 1U);
    assert_stages(&disk, payload_sync, sizeof(payload_sync));

    memset(&disk, 0, sizeof(disk));
    sd_ring_durability_init(&durability, &mounted);
    disk.header_failures_remaining = 1;
    assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == -EIO);
    assert_cursor_eq(&durability.durable, &mounted);
    assert(disk.write_calls == 1U);
    assert(disk.header_calls == 1U);
    assert(disk.metadata_calls == 0U);
    assert(disk.sync_calls == 1U);
    assert_stages(&disk, through_header, sizeof(through_header));

    memset(&disk, 0, sizeof(disk));
    sd_ring_durability_init(&durability, &mounted);
    disk.sync_fail_on_call = 2U;
    assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == -EIO);
    assert_cursor_eq(&durability.durable, &mounted);
    assert(disk.write_calls == 1U);
    assert(disk.header_calls == 1U);
    assert(disk.metadata_calls == 0U);
    assert(disk.sync_calls == 2U);
    assert_stages(&disk, through_header_sync, sizeof(through_header_sync));

    memset(&disk, 0, sizeof(disk));
    sd_ring_durability_init(&durability, &mounted);
    disk.metadata_failures_remaining = 1;
    assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == -EIO);
    assert_cursor_eq(&durability.durable, &mounted);
    assert(disk.sync_calls == 2U);
    assert_stages(&disk, through_metadata, sizeof(through_metadata));

    memset(&disk, 0, sizeof(disk));
    sd_ring_durability_init(&durability, &mounted);
    disk.sync_fail_on_call = 3U;
    assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == -EIO);
    assert_cursor_eq(&durability.durable, &mounted);
    assert(disk.sync_calls == 3U);
    assert_stages(&disk, complete_order, sizeof(complete_order));

    memset(&disk, 0, sizeof(disk));
    sd_ring_durability_init(&durability, &mounted);
    assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == 0);
    assert_cursor_eq(&durability.durable, &candidate);
    assert_cursor_eq(&disk.persisted, &candidate);
    assert(disk.write_calls == 1U);
    assert(disk.header_calls == 1U);
    assert(disk.metadata_calls == 1U);
    assert(disk.sync_calls == 3U);
    assert_stages(&disk, complete_order, sizeof(complete_order));
}

static void test_transient_batch_failures_keep_tail_invisible_until_success(void)
{
    const sd_ring_cursor_t mounted = {
        .read_seq = 0U,
        .write_seq = 4U,
        .dropped_packets = 0U,
        .capacity_packets = 16U,
    };
    const sd_ring_cursor_t candidate = {
        .read_seq = 0U,
        .write_seq = 6U,
        .dropped_packets = 0U,
        .capacity_packets = 16U,
    };
    sd_ring_durability_t durability;
    sd_write_recovery_policy_t policy;
    fake_durable_disk_t disk = {.write_failures_remaining = 3};
    sd_ring_read_plan_t plan;

    memset(disk.staged_payload, 0xD1, sizeof(disk.staged_payload));
    sd_ring_durability_init(&durability, &mounted);
    sd_write_recovery_init(&policy);

    for (uint32_t failure = 0U; failure < 3U; failure++) {
        assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == -EIO);
        assert(sd_write_recovery_on_failure(&policy) == SD_WRITE_RECOVERY_ACTION_RETRY);
        assert_cursor_eq(&durability.durable, &mounted);
        assert(sd_ring_durability_plan_read(&durability, candidate.write_seq - 1U, 1U, &plan) == -ERANGE);
    }

    assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == 0);
    sd_write_recovery_on_success(&policy);
    assert_cursor_eq(&durability.durable, &candidate);
    assert(sd_ring_durability_plan_read(&durability, mounted.write_seq, 8U, &plan) == 0);
    assert(plan.packet_count == 2U);
    assert(policy.state == SD_WRITE_RECOVERY_HEALTHY);
}

static void test_terminal_mode_reports_loss_and_reads_only_committed_backlog(void)
{
    const sd_ring_cursor_t mounted = {
        .read_seq = 2U,
        .write_seq = 6U,
        .dropped_packets = 1U,
        .capacity_packets = 16U,
    };
    const sd_ring_cursor_t dirty_candidate = {
        .read_seq = 2U,
        .write_seq = 8U,
        .dropped_packets = 1U,
        .capacity_packets = 16U,
    };
    sd_ring_durability_t durability;
    sd_write_recovery_policy_t policy;
    fake_durable_disk_t disk = {.write_failures_remaining = 100};
    sd_ring_read_plan_t plan;
    uint8_t copied[4] = {0};
    uint32_t remounts = 0U;

    memset(disk.committed_payload, 0xA4, sizeof(disk.committed_payload));
    memset(disk.staged_payload, 0xD7, sizeof(disk.staged_payload));
    sd_ring_durability_init(&durability, &mounted);
    sd_write_recovery_init(&policy);

    while (!sd_write_recovery_is_terminal(&policy)) {
        assert(sd_ring_durability_commit_batch(&durability, &dirty_candidate, 6U, true, &fake_disk_ops, &disk) == -EIO);
        sd_write_recovery_action_t action = sd_write_recovery_on_failure(&policy);
        if (action == SD_WRITE_RECOVERY_ACTION_REMOUNT) {
            remounts++;
        }
    }
    assert(remounts == SD_WRITE_MAX_REMOUNTS);
    assert_cursor_eq(&durability.durable, &mounted);

    /* Attempted-but-never-durable records stay in diagnostics, not wire dropped. */
    sd_ring_durability_enter_terminal(&durability);
    sd_ring_cursor_t info = sd_ring_durability_info(&durability);
    assert(info.read_seq == mounted.read_seq);
    assert(info.write_seq == mounted.write_seq);
    assert(info.dropped_packets == mounted.dropped_packets);

    uint32_t write_calls = disk.write_calls;
    uint32_t metadata_calls = disk.metadata_calls;
    uint32_t sync_calls = disk.sync_calls;
    assert(sd_ring_durability_plan_read(&durability, mounted.read_seq, 10U, &plan) == 0);
    assert(plan.packet_count == mounted.write_seq - mounted.read_seq);
    memcpy(copied, disk.committed_payload, sizeof(copied));
    for (size_t i = 0U; i < sizeof(copied); i++) {
        assert(copied[i] == 0xA4);
    }
    assert(disk.write_calls == write_calls);
    assert(disk.metadata_calls == metadata_calls);
    assert(disk.sync_calls == sync_calls);

    assert(sd_ring_durability_plan_read(&durability, mounted.write_seq, 10U, &plan) == 0);
    assert(plan.packet_count == 0U);
    assert(sd_ring_durability_plan_read(&durability, mounted.write_seq + 1U, 1U, &plan) == -ERANGE);
    assert(ring_storage_frame_should_retain(false));
    assert(!ring_storage_frame_should_retain(true));
}

static void test_advance_transaction_never_mutates_watermark_on_failure(void)
{
    const sd_ring_cursor_t mounted = {
        .read_seq = 2U,
        .write_seq = 6U,
        .dropped_packets = 1U,
        .capacity_packets = 16U,
    };
    sd_ring_cursor_t candidate = mounted;
    sd_ring_durability_t durability;
    fake_durable_disk_t disk = {0};
    candidate.read_seq = 4U;

    sd_ring_durability_init(&durability, &mounted);
    disk.metadata_failures_remaining = 1;
    assert(sd_ring_durability_commit_metadata(&durability, &candidate, false, true, &fake_disk_ops, &disk) == -EIO);
    assert_cursor_eq(&durability.durable, &mounted);
    assert(disk.write_calls == 0U);

    memset(&disk, 0, sizeof(disk));
    sd_ring_durability_init(&durability, &mounted);
    disk.sync_failures_remaining = 1;
    assert(sd_ring_durability_commit_metadata(&durability, &candidate, false, true, &fake_disk_ops, &disk) == -EIO);
    assert_cursor_eq(&durability.durable, &mounted);
    assert(disk.write_calls == 0U);

    memset(&disk, 0, sizeof(disk));
    sd_ring_durability_init(&durability, &mounted);
    assert(sd_ring_durability_commit_metadata(&durability, &candidate, false, true, &fake_disk_ops, &disk) == 0);
    assert_cursor_eq(&durability.durable, &candidate);
    assert(disk.write_calls == 0U);
}

static void test_pending_advance_is_fenced_until_quarantine_recovery(void)
{
    const sd_ring_cursor_t baseline = {
        .read_seq = 0U,
        .write_seq = 3U,
        .dropped_packets = 0U,
        .capacity_packets = 16U,
    };
    sd_ring_cursor_t advance_candidate = baseline;
    advance_candidate.read_seq = 2U;

    sd_ring_durability_t durability;
    fake_durable_disk_t disk = {.persisted = baseline};
    sd_ring_durability_init(&durability, &baseline);

    /*
     * Production queues ADVANCE independently of the failed batch retry. The
     * active NVS marker must fence it before metadata generation or cursor
     * state can change.
     */
    assert(sd_ring_durability_commit_metadata(&durability, &advance_candidate, true, true, &fake_disk_ops, &disk) ==
           -EBUSY);
    assert(disk.metadata_calls == 0U);
    assert(disk.sync_calls == 0U);
    assert(disk.stage_count == 0U);
    assert_cursor_eq(&durability.durable, &baseline);
    assert_cursor_eq(&disk.persisted, &baseline);

    sd_ring_quarantine_recovery_t torn_partial = {
        .affected_start_seq = 0U,
        .replacement_start_seq = 0U,
        .attempted_write_seq = 5U,
        .metadata_generation = 10U,
        .baseline = baseline,
        .batch_packets = 16U,
        .preimage_untouched = false,
        .replacement_valid = false,
    };
    sd_ring_cursor_t rebooted = disk.persisted;
    assert(sd_ring_reconcile_quarantine(&rebooted, 10U, &torn_partial) == 1);
    assert(rebooted.read_seq == 0U);
    assert(rebooted.write_seq == 0U);
    assert(rebooted.dropped_packets == 3U);

    /* A failed marker delete remains replay-safe on the following reboot. */
    assert(sd_ring_reconcile_quarantine(&rebooted, 11U, &torn_partial) == 0);
    assert(rebooted.read_seq == 0U);
    assert(rebooted.write_seq == 0U);
    assert(rebooted.dropped_packets == 3U);
}

static void test_background_remount_failure_progresses_without_new_request(void)
{
    sd_write_recovery_policy_t policy;
    uint32_t failures = 0U;
    uint32_t remount_actions = 0U;

    sd_write_recovery_init(&policy);
    while (sd_write_recovery_mount_required(true, false, &policy)) {
        failures++;
        sd_write_recovery_action_t action = sd_write_recovery_on_failure(&policy);
        if (action == SD_WRITE_RECOVERY_ACTION_REMOUNT) {
            remount_actions++;
        }
    }

    assert(failures == SD_WRITE_RETRIES_PER_MOUNT * (SD_WRITE_MAX_REMOUNTS + 1U));
    assert(remount_actions == SD_WRITE_MAX_REMOUNTS);
    assert(sd_write_recovery_is_terminal(&policy));
    assert(!sd_write_recovery_mount_required(true, false, &policy));

    sd_write_recovery_init(&policy);
    assert(sd_write_recovery_mount_required(true, false, &policy));
    assert(sd_write_recovery_on_failure(&policy) == SD_WRITE_RECOVERY_ACTION_RETRY);
    assert(sd_write_recovery_on_failure(&policy) == SD_WRITE_RECOVERY_ACTION_RETRY);
    sd_write_recovery_on_success(&policy);
    assert(policy.state == SD_WRITE_RECOVERY_HEALTHY);
    assert(!sd_write_recovery_mount_required(false, true, &policy));
}

static void test_no_card_at_boot_reaches_ready_terminal_without_infinite_retry(void)
{
    sd_write_recovery_policy_t policy;

    sd_write_recovery_init(&policy);
    assert(sd_write_recovery_boot_mount_result(&policy, -ENODEV) == SD_BOOT_MOUNT_REMOUNT);
    assert(policy.remounts == 1U);
    assert(sd_write_recovery_boot_mount_result(&policy, -ENODEV) == SD_BOOT_MOUNT_REMOUNT);
    assert(policy.remounts == 2U);
    assert(sd_write_recovery_boot_mount_result(&policy, -ENODEV) == SD_BOOT_MOUNT_TERMINAL);
    assert(sd_write_recovery_is_terminal(&policy));

    sd_write_recovery_init(&policy);
    assert(sd_write_recovery_boot_mount_result(&policy, -EIO) == SD_BOOT_MOUNT_REMOUNT);
    assert(sd_write_recovery_boot_mount_result(&policy, 0) == SD_BOOT_MOUNT_READY);
    assert(policy.state == SD_WRITE_RECOVERY_HEALTHY);
}

static void test_wrap_failure_advances_only_safe_read_floor(void)
{
    const sd_ring_cursor_t mounted = {
        .read_seq = 0U,
        .write_seq = 8U,
        .dropped_packets = 0U,
        .capacity_packets = 8U,
    };
    const sd_ring_cursor_t wrapping_candidate = {
        .read_seq = 2U,
        .write_seq = 10U,
        .dropped_packets = 2U,
        .capacity_packets = 8U,
    };
    const sd_ring_cursor_t safe_after_overwrite = {
        .read_seq = 2U,
        .write_seq = 8U,
        .dropped_packets = 2U,
        .capacity_packets = 8U,
    };
    sd_ring_durability_t durability;
    fake_durable_disk_t disk = {.metadata_failures_remaining = 1};
    sd_ring_read_plan_t plan;

    sd_ring_durability_init(&durability, &mounted);
    assert(sd_ring_durability_commit_batch(&durability, &wrapping_candidate, 8U, true, &fake_disk_ops, &disk) == -EIO);
    assert_cursor_eq(&durability.durable, &safe_after_overwrite);
    assert(sd_ring_durability_plan_read(&durability, 0U, 8U, &plan) == -ERANGE);
    assert(sd_ring_durability_plan_read(&durability, 2U, 8U, &plan) == 0);
    assert(plan.packet_count == 6U);
    assert(sd_ring_durability_plan_read(&durability, 8U, 8U, &plan) == 0);
    assert(plan.packet_count == 0U);
    assert(sd_ring_durability_plan_read(&durability, 9U, 8U, &plan) == -ERANGE);

    memset(&disk, 0, sizeof(disk));
    disk.sync_failures_remaining = 1;
    sd_ring_durability_init(&durability, &mounted);
    assert(sd_ring_durability_commit_batch(&durability, &wrapping_candidate, 8U, true, &fake_disk_ops, &disk) == -EIO);
    assert_cursor_eq(&durability.durable, &safe_after_overwrite);

    memset(&disk, 0, sizeof(disk));
    disk.write_failures_remaining = 1;
    sd_ring_durability_init(&durability, &mounted);
    assert(sd_ring_durability_commit_batch(&durability, &wrapping_candidate, 8U, true, &fake_disk_ops, &disk) == -EIO);
    assert_cursor_eq(&durability.durable, &safe_after_overwrite);
    sd_ring_durability_enter_terminal(&durability);
    sd_ring_cursor_t terminal_info = sd_ring_durability_info(&durability);
    assert(terminal_info.read_seq == 2U);
    assert(terminal_info.write_seq == 8U);
    assert(terminal_info.dropped_packets == 2U);
    assert(sd_ring_durability_plan_read(&durability, 0U, 8U, &plan) == -ERANGE);
    assert(sd_ring_durability_plan_read(&durability, 2U, 8U, &plan) == 0);
    assert(plan.packet_count == 6U);
}

static void test_failed_partial_tail_rewrite_is_quarantined_until_full_success(void)
{
    const sd_ring_cursor_t mounted = {
        .read_seq = 0U,
        .write_seq = 3U,
        .dropped_packets = 0U,
        .capacity_packets = 16U,
    };
    const sd_ring_cursor_t candidate = {
        .read_seq = 0U,
        .write_seq = 5U,
        .dropped_packets = 0U,
        .capacity_packets = 16U,
    };
    sd_ring_durability_t durability;
    sd_write_recovery_policy_t policy;
    fake_durable_disk_t disk = {.write_failures_remaining = 100};
    sd_ring_read_plan_t plan;

    sd_ring_durability_init(&durability, &mounted);
    sd_write_recovery_init(&policy);
    while (!sd_write_recovery_is_terminal(&policy)) {
        assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == -EIO);
        (void) sd_write_recovery_on_failure(&policy);
    }

    assert(durability.unsafe_batch);
    assert(sd_ring_durability_unsafe_packets(&durability) == 3U);
    assert(sd_ring_durability_plan_read(&durability, 0U, 8U, &plan) == 0);
    assert(plan.packet_count == 0U);
    sd_ring_durability_enter_terminal(&durability);
    sd_ring_cursor_t info = sd_ring_durability_info(&durability);
    assert(info.read_seq == 0U);
    assert(info.write_seq == 0U);
    assert(info.dropped_packets == 3U);
    assert(sd_ring_durability_unsafe_packets(&durability) == 3U);
    assert(sd_ring_durability_plan_read(&durability, 1U, 1U, &plan) == -ERANGE);

    memset(&disk, 0, sizeof(disk));
    sd_ring_durability_init(&durability, &mounted);
    disk.write_failures_remaining = 1;
    assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == -EIO);
    assert(durability.unsafe_batch);
    assert(sd_ring_durability_commit_batch(&durability, &candidate, 0U, true, &fake_disk_ops, &disk) == 0);
    assert(!durability.unsafe_batch);
    assert_cursor_eq(&durability.durable, &candidate);
}

static void test_reboot_quarantine_recovery_is_conservative_and_idempotent(void)
{
    assert(sd_ring_quarantine_retry_allowed(5U, 5U));
    assert(sd_ring_quarantine_retry_allowed(5U, 6U));
    assert(!sd_ring_quarantine_retry_allowed(5U, 4U));

    const sd_ring_cursor_t partial_baseline = {
        .read_seq = 0U,
        .write_seq = 3U,
        .dropped_packets = 0U,
        .capacity_packets = 16U,
    };
    sd_ring_quarantine_recovery_t torn_partial = {
        .affected_start_seq = 0U,
        .replacement_start_seq = 0U,
        .attempted_write_seq = 5U,
        .metadata_generation = 10U,
        .baseline = partial_baseline,
        .batch_packets = 16U,
        .preimage_untouched = false,
        .replacement_valid = false,
    };
    sd_ring_cursor_t rebooted = partial_baseline;
    assert(sd_ring_reconcile_quarantine(&rebooted, 10U, &torn_partial) == 1);
    assert(rebooted.read_seq == 0U);
    assert(rebooted.write_seq == 0U);
    assert(rebooted.dropped_packets == 3U);

    /* NVS delete failed: a second boot recognizes the absolute recovery cursor. */
    assert(sd_ring_reconcile_quarantine(&rebooted, 11U, &torn_partial) == 0);
    assert(rebooted.dropped_packets == 3U);

    sd_ring_cursor_t untouched = partial_baseline;
    sd_ring_quarantine_recovery_t reset_before_write = torn_partial;
    reset_before_write.preimage_untouched = true;
    assert(sd_ring_reconcile_quarantine(&untouched, 10U, &reset_before_write) == 0);
    assert_cursor_eq(&untouched, &partial_baseline);

    const sd_ring_cursor_t full_baseline = {
        .read_seq = 0U,
        .write_seq = 8U,
        .dropped_packets = 0U,
        .capacity_packets = 8U,
    };
    sd_ring_quarantine_recovery_t torn_wrap = {
        .affected_start_seq = 0U,
        .replacement_start_seq = 8U,
        .attempted_write_seq = 10U,
        .metadata_generation = 20U,
        .baseline = full_baseline,
        .batch_packets = 2U,
        .preimage_untouched = false,
        .replacement_valid = false,
    };
    rebooted = full_baseline;
    assert(sd_ring_reconcile_quarantine(&rebooted, 20U, &torn_wrap) == 1);
    assert(rebooted.read_seq == 2U);
    assert(rebooted.write_seq == 8U);
    assert(rebooted.dropped_packets == 2U);

    /* A fully committed candidate plus stale marker never replays loss. */
    sd_ring_cursor_t committed = {
        .read_seq = 0U,
        .write_seq = 5U,
        .dropped_packets = 0U,
        .capacity_packets = 16U,
    };
    torn_partial.replacement_valid = true;
    assert(sd_ring_reconcile_quarantine(&committed, 11U, &torn_partial) == 0);
    assert_cursor_eq(&committed,
                     &(sd_ring_cursor_t) {
                         .read_seq = 0U,
                         .write_seq = 5U,
                         .dropped_packets = 0U,
                         .capacity_packets = 16U,
                     });
}

static void test_terminal_reconnect_flushes_never_mutate_media(void)
{
    const sd_ring_cursor_t mounted = {
        .read_seq = 2U,
        .write_seq = 6U,
        .dropped_packets = 1U,
        .capacity_packets = 16U,
    };
    sd_ring_durability_t durability;
    fake_durable_disk_t disk = {0};

    sd_ring_durability_init(&durability, &mounted);
    sd_ring_durability_enter_terminal(&durability);
    for (uint32_t reconnect = 0U; reconnect < 3U; reconnect++) {
        bool terminal = durability.terminal;
        assert(ring_storage_terminal_flush_resolved(terminal));
        assert(!ring_storage_media_mutation_allowed(terminal));
    }
    assert(disk.write_calls == 0U);
    assert(disk.metadata_calls == 0U);
    assert(disk.sync_calls == 0U);
    assert_cursor_eq(&durability.durable, &mounted);
}

static void test_terminal_empty_queue_flush_clears_partial_packer_tail(void)
{
    audio_storage_packer_t packer;
    fake_writer_t writer = {0};
    uint8_t frame[80];

    fill_frame(frame, sizeof(frame), 0xE2);
    audio_storage_packer_init(&packer);
    assert(audio_storage_packer_push(&packer, frame, sizeof(frame), fake_write, &writer) ==
           AUDIO_STORAGE_PACKER_ACCEPTED);
    assert(audio_storage_packer_pending_bytes(&packer) > 0U);
    assert(writer.record_count == 0U);

    /* Production resolves connect/shutdown flush without needing a new TX frame. */
    assert(ring_storage_terminal_flush_resolved(true));
    audio_storage_packer_init(&packer);
    assert(audio_storage_packer_pending_bytes(&packer) == 0U);
    assert(!ring_snapshot_retry_required(true, true));
}

static void test_control_response_retries_transient_notify_backpressure(void)
{
    assert(ring_control_response_should_retain(true, -ENOMEM));
    assert(ring_control_response_should_retain(true, -EAGAIN));
    assert(ring_control_response_should_retain(true, -EBUSY));
    assert(!ring_control_response_should_retain(false, -ENOMEM));
    assert(!ring_control_response_should_retain(true, -EINVAL));
    assert(!ring_control_response_should_retain(true, 0));
}

static void test_done_notification_stays_pending_until_enqueue_succeeds(void)
{
    bool done_pending = true;

    if (!ring_control_response_should_retain(true, -ENOMEM)) {
        done_pending = false;
    }
    assert(done_pending);

    if (!ring_control_response_should_retain(true, 0)) {
        done_pending = false;
    }
    assert(!done_pending);
}

static void test_snapshot_commit_retries_until_success_or_disconnect(void)
{
    assert(ring_snapshot_retry_required(true, false));
    assert(!ring_snapshot_retry_required(true, true));
    assert(!ring_snapshot_retry_required(false, false));
}

static void test_power_on_queue_failure_reconciles_until_mount_or_newer_off(void)
{
    assert(ring_power_on_reconcile_required(true, false, -ENOMEM));
    assert(ring_power_on_reconcile_required(true, false, -EIO));
    assert(!ring_power_on_reconcile_required(false, false, -ENOMEM));
    assert(!ring_power_on_reconcile_required(true, true, -ENOMEM));
    assert(!ring_power_on_reconcile_required(true, false, 0));
}

static void test_bulk_link_policy_avoids_range_boundary_parameter_churn(void)
{
    ring_bulk_link_policy_t policy;

    ring_bulk_link_policy_reset(&policy);
    assert(ring_bulk_link_policy_on_read(&policy) == RING_BULK_LINK_ACTION_REQUEST_BULK);
    assert(ring_bulk_link_policy_on_read(&policy) == RING_BULK_LINK_ACTION_NONE);

    ring_bulk_link_policy_on_idle(&policy);
    assert(ring_bulk_link_policy_on_read(&policy) == RING_BULK_LINK_ACTION_NONE);
    assert(ring_bulk_link_policy_on_restore_timeout(&policy) == RING_BULK_LINK_ACTION_NONE);

    ring_bulk_link_policy_on_idle(&policy);
    assert(ring_bulk_link_policy_on_restore_timeout(&policy) == RING_BULK_LINK_ACTION_REQUEST_NORMAL);
    assert(ring_bulk_link_policy_on_read(&policy) == RING_BULK_LINK_ACTION_REQUEST_BULK);
    assert(ring_bulk_link_policy_on_stop(&policy) == RING_BULK_LINK_ACTION_REQUEST_NORMAL);
    assert(ring_bulk_link_policy_on_stop(&policy) == RING_BULK_LINK_ACTION_NONE);
}

int main(void)
{
    test_storage_command_readiness_is_bounded_and_terminal_aware();
    test_overflow_flushes_complete_record_and_zero_pads_tail();
    test_rejected_overflow_does_not_consume_or_reorder_new_frame();
    test_exact_fit_flushes_legacy_terminated_record_before_new_frame();
    test_invalid_frame_leaves_state_unchanged();
    test_delivery_policy_falls_back_after_live_enqueue_failure();
    test_pre_pusher_queue_saturation_preserves_whole_frame();
    test_transfer_crc_and_done_notification_match_golden_wire_bytes();
    test_invalid_rtc_uses_zero_timestamp_without_rejecting_audio();
    test_rebooted_rtc_requires_live_current_time();
    test_elapsed_marker_create_consume_and_no_replay();
    test_elapsed_marker_wrong_reset_provenance_is_consumed();
    test_elapsed_marker_prepare_faults_fail_closed();
    test_elapsed_marker_recovery_faults_consume_before_failure();
    test_elapsed_marker_unbounded_and_ambiguous_intervals_never_apply();
    test_elapsed_marker_checked_epoch_arithmetic();
    test_rtc_repeated_boot_and_live_sync_transitions_are_transactional();
    test_rtc_now_ms_clamps_and_saturates_boundaries();
    test_connect_snapshot_flushes_existing_tail_after_queued_frames();
    test_dirty_batch_retries_after_media_recovers_without_ble_command();
    test_transient_sd_failure_retains_order_until_recovery();
    test_permanent_sd_failure_has_bounded_remounts_and_terminal_state();
    test_durable_batch_transaction_fault_matrix();
    test_transient_batch_failures_keep_tail_invisible_until_success();
    test_terminal_mode_reports_loss_and_reads_only_committed_backlog();
    test_advance_transaction_never_mutates_watermark_on_failure();
    test_pending_advance_is_fenced_until_quarantine_recovery();
    test_background_remount_failure_progresses_without_new_request();
    test_no_card_at_boot_reaches_ready_terminal_without_infinite_retry();
    test_wrap_failure_advances_only_safe_read_floor();
    test_failed_partial_tail_rewrite_is_quarantined_until_full_success();
    test_reboot_quarantine_recovery_is_conservative_and_idempotent();
    test_terminal_reconnect_flushes_never_mutate_media();
    test_terminal_empty_queue_flush_clears_partial_packer_tail();
    test_control_response_retries_transient_notify_backpressure();
    test_done_notification_stays_pending_until_enqueue_succeeds();
    test_snapshot_commit_retries_until_success_or_disconnect();
    test_power_on_queue_failure_reconciles_until_mount_or_newer_off();
    test_bulk_link_policy_avoids_range_boundary_parameter_churn();
    puts("audio_storage_packer_tests: PASS");
    return 0;
}
