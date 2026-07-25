#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

#include "../../src/lib/core/audio_storage_packer.h"
#include "../../src/lib/core/ring_transfer_integrity.h"

#define MAX_CAPTURED_RECORDS 4U

typedef struct {
    uint8_t records[MAX_CAPTURED_RECORDS][AUDIO_STORAGE_RECORD_BYTES];
    size_t record_count;
    size_t rejected_writes;
} fake_writer_t;

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

static void test_control_response_retries_transient_notify_backpressure(void)
{
    assert(ring_control_response_should_retain(true, -ENOMEM));
    assert(ring_control_response_should_retain(true, -EAGAIN));
    assert(ring_control_response_should_retain(true, -EBUSY));
    assert(!ring_control_response_should_retain(false, -ENOMEM));
    assert(!ring_control_response_should_retain(true, -EINVAL));
    assert(!ring_control_response_should_retain(true, 0));
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

int main(void)
{
    test_overflow_flushes_complete_record_and_zero_pads_tail();
    test_rejected_overflow_does_not_consume_or_reorder_new_frame();
    test_exact_fit_flushes_legacy_terminated_record_before_new_frame();
    test_invalid_frame_leaves_state_unchanged();
    test_delivery_policy_falls_back_after_live_enqueue_failure();
    test_pre_pusher_queue_saturation_preserves_whole_frame();
    test_transfer_crc_and_done_notification_match_golden_wire_bytes();
    test_invalid_rtc_uses_zero_timestamp_without_rejecting_audio();
    test_connect_snapshot_flushes_existing_tail_after_queued_frames();
    test_dirty_batch_retries_after_media_recovers_without_ble_command();
    test_control_response_retries_transient_notify_backpressure();
    test_snapshot_commit_retries_until_success_or_disconnect();
    test_power_on_queue_failure_reconciles_until_mount_or_newer_off();
    puts("audio_storage_packer_tests: PASS");
    return 0;
}
