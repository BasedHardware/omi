#include "sd_read_recovery.h"

#include <errno.h>
#include <stddef.h>

static int read_single_sectors(sd_sector_read_fn read_sectors,
                               void *context,
                               uint8_t *buffer,
                               uint32_t start_sector,
                               uint32_t sector_count,
                               uint32_t sector_size,
                               struct sd_read_recovery_metrics *metrics)
{
    for (uint32_t index = 0; index < sector_count; index++) {
        uint32_t sector = start_sector + index;
        int ret = read_sectors(context, buffer + ((size_t) index * sector_size), sector, 1U);
        if (ret != 0) {
            metrics->fallback_sector_failures++;
            metrics->last_fallback_error = ret;
            metrics->last_failed_sector = sector;
            return ret;
        }
    }

    metrics->last_fallback_error = 0;
    return 0;
}

int sd_read_batch_with_sector_fallback(sd_sector_read_fn read_sectors,
                                       void *context,
                                       uint8_t *buffer,
                                       uint32_t start_sector,
                                       uint32_t sector_count,
                                       uint32_t sector_size,
                                       struct sd_read_recovery_metrics *metrics)
{
    if (!read_sectors || !buffer || !metrics || sector_count == 0U || sector_size == 0U) {
        return -EINVAL;
    }

    if (metrics->magic != SD_READ_RECOVERY_DIAG_MAGIC) {
        *metrics = (struct sd_read_recovery_metrics) {
            .magic = SD_READ_RECOVERY_DIAG_MAGIC,
        };
    }
    metrics->last_start_sector = start_sector;

    if (metrics->single_sector_mode != 0U) {
        metrics->single_sector_batches++;
        return read_single_sectors(read_sectors, context, buffer, start_sector, sector_count, sector_size, metrics);
    }

    int ret = read_sectors(context, buffer, start_sector, sector_count);
    if (ret == 0) {
        return 0;
    }

    metrics->multiblock_failures++;
    metrics->last_multiblock_error = ret;
    metrics->fallback_attempts++;

    ret = read_single_sectors(read_sectors, context, buffer, start_sector, sector_count, sector_size, metrics);
    if (ret != 0) {
        return ret;
    }

    metrics->recovered_batches++;
    metrics->single_sector_mode = 1U;
    return 0;
}
