#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "sd_read_recovery.h"

#define TEST_SECTOR_SIZE 8U
#define TEST_SECTOR_COUNT 4U
#define TEST_START_SECTOR 100U

struct read_call {
    uint8_t *buffer;
    uint32_t start_sector;
    uint32_t sector_count;
};

struct scripted_io {
    int results[(1U + TEST_SECTOR_COUNT) * 2U];
    size_t result_count;
    size_t result_index;
    struct read_call calls[(1U + TEST_SECTOR_COUNT) * 2U];
};

static int scripted_read(void *context, uint8_t *buffer, uint32_t start_sector, uint32_t sector_count)
{
    struct scripted_io *io = context;
    assert(io->result_index < io->result_count);
    io->calls[io->result_index] = (struct read_call) {
        .buffer = buffer,
        .start_sector = start_sector,
        .sector_count = sector_count,
    };

    int ret = io->results[io->result_index++];
    if (ret == 0) {
        memset(buffer, (int) start_sector, sector_count * TEST_SECTOR_SIZE);
    }
    return ret;
}

static void
assert_fallback_call(const struct scripted_io *io, const uint8_t *buffer, size_t call_index, uint32_t sector_index)
{
    assert(io->calls[call_index].buffer == buffer + (sector_index * TEST_SECTOR_SIZE));
    assert(io->calls[call_index].start_sector == TEST_START_SECTOR + sector_index);
    assert(io->calls[call_index].sector_count == 1U);
}

static void test_success_uses_one_multiblock_read(void)
{
    uint8_t buffer[TEST_SECTOR_SIZE * TEST_SECTOR_COUNT] = {0};
    struct scripted_io io = {.results = {0}, .result_count = 1U};
    struct sd_read_recovery_metrics metrics = {0};

    assert(sd_read_batch_with_sector_fallback(
               scripted_read, &io, buffer, TEST_START_SECTOR, TEST_SECTOR_COUNT, TEST_SECTOR_SIZE, &metrics) == 0);
    assert(io.result_index == 1U);
    assert(io.calls[0].buffer == buffer);
    assert(io.calls[0].start_sector == TEST_START_SECTOR);
    assert(io.calls[0].sector_count == TEST_SECTOR_COUNT);
    assert(metrics.magic == SD_READ_RECOVERY_DIAG_MAGIC);
    assert(metrics.multiblock_failures == 0U);
    assert(metrics.fallback_attempts == 0U);
    assert(metrics.last_start_sector == TEST_START_SECTOR);
}

static void test_persistent_multiblock_error_recovers_with_single_sector_reads(void)
{
    uint8_t buffer[TEST_SECTOR_SIZE * TEST_SECTOR_COUNT] = {0};
    struct scripted_io io = {
        .results = {-EIO, 0, 0, 0, 0},
        .result_count = 1U + TEST_SECTOR_COUNT,
    };
    struct sd_read_recovery_metrics metrics = {0};

    assert(sd_read_batch_with_sector_fallback(
               scripted_read, &io, buffer, TEST_START_SECTOR, TEST_SECTOR_COUNT, TEST_SECTOR_SIZE, &metrics) == 0);
    assert(io.result_index == 1U + TEST_SECTOR_COUNT);
    for (uint32_t index = 0; index < TEST_SECTOR_COUNT; index++) {
        assert_fallback_call(&io, buffer, 1U + index, index);
        for (uint32_t byte = 0; byte < TEST_SECTOR_SIZE; byte++) {
            assert(buffer[(index * TEST_SECTOR_SIZE) + byte] == (uint8_t) (TEST_START_SECTOR + index));
        }
    }
    assert(metrics.multiblock_failures == 1U);
    assert(metrics.last_multiblock_error == -EIO);
    assert(metrics.fallback_attempts == 1U);
    assert(metrics.fallback_sector_failures == 0U);
    assert(metrics.last_fallback_error == 0);
    assert(metrics.recovered_batches == 1U);
    assert(metrics.single_sector_mode == 1U);
    assert(metrics.single_sector_batches == 0U);
}

static void test_successful_fallback_latches_single_sector_mode(void)
{
    uint8_t first_buffer[TEST_SECTOR_SIZE * TEST_SECTOR_COUNT] = {0};
    uint8_t second_buffer[TEST_SECTOR_SIZE * TEST_SECTOR_COUNT] = {0};
    struct scripted_io io = {
        .results = {-EIO, 0, 0, 0, 0, 0, 0, 0, 0},
        .result_count = 1U + (2U * TEST_SECTOR_COUNT),
    };
    struct sd_read_recovery_metrics metrics = {0};

    assert(sd_read_batch_with_sector_fallback(
               scripted_read, &io, first_buffer, TEST_START_SECTOR, TEST_SECTOR_COUNT, TEST_SECTOR_SIZE, &metrics) ==
           0);
    assert(sd_read_batch_with_sector_fallback(scripted_read,
                                              &io,
                                              second_buffer,
                                              TEST_START_SECTOR + TEST_SECTOR_COUNT,
                                              TEST_SECTOR_COUNT,
                                              TEST_SECTOR_SIZE,
                                              &metrics) == 0);

    assert(io.result_index == 1U + (2U * TEST_SECTOR_COUNT));
    for (uint32_t index = 0; index < TEST_SECTOR_COUNT; index++) {
        size_t call_index = 1U + TEST_SECTOR_COUNT + index;
        assert(io.calls[call_index].buffer == second_buffer + (index * TEST_SECTOR_SIZE));
        assert(io.calls[call_index].start_sector == TEST_START_SECTOR + TEST_SECTOR_COUNT + index);
        assert(io.calls[call_index].sector_count == 1U);
    }
    assert(metrics.multiblock_failures == 1U);
    assert(metrics.fallback_attempts == 1U);
    assert(metrics.recovered_batches == 1U);
    assert(metrics.single_sector_mode == 1U);
    assert(metrics.single_sector_batches == 1U);
}

static void test_single_sector_failure_stops_without_accepting_batch(void)
{
    uint8_t buffer[TEST_SECTOR_SIZE * TEST_SECTOR_COUNT] = {0};
    struct scripted_io io = {
        .results = {-EIO, 0, 0, -EILSEQ},
        .result_count = 4U,
    };
    struct sd_read_recovery_metrics metrics = {0};

    assert(sd_read_batch_with_sector_fallback(
               scripted_read, &io, buffer, TEST_START_SECTOR, TEST_SECTOR_COUNT, TEST_SECTOR_SIZE, &metrics) ==
           -EILSEQ);
    assert(io.result_index == 4U);
    assert_fallback_call(&io, buffer, 1U, 0U);
    assert_fallback_call(&io, buffer, 2U, 1U);
    assert_fallback_call(&io, buffer, 3U, 2U);
    assert(metrics.multiblock_failures == 1U);
    assert(metrics.fallback_attempts == 1U);
    assert(metrics.fallback_sector_failures == 1U);
    assert(metrics.last_fallback_error == -EILSEQ);
    assert(metrics.last_failed_sector == TEST_START_SECTOR + 2U);
    assert(metrics.recovered_batches == 0U);
}

static void test_invalid_request_does_not_touch_metrics(void)
{
    uint8_t buffer[TEST_SECTOR_SIZE] = {0};
    struct scripted_io io = {0};
    struct sd_read_recovery_metrics metrics = {0};

    assert(sd_read_batch_with_sector_fallback(
               scripted_read, &io, buffer, TEST_START_SECTOR, 0U, TEST_SECTOR_SIZE, &metrics) == -EINVAL);
    assert(metrics.magic == 0U);
    assert(io.result_index == 0U);
}

int main(void)
{
    test_success_uses_one_multiblock_read();
    test_persistent_multiblock_error_recovers_with_single_sector_reads();
    test_successful_fallback_latches_single_sector_mode();
    test_single_sector_failure_stops_without_accepting_batch();
    test_invalid_request_does_not_touch_metrics();
    puts("plus57 SD single-sector fallback tests passed");
    return 0;
}
