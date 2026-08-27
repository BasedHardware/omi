#ifndef SD_READ_RECOVERY_H
#define SD_READ_RECOVERY_H

#include <stdint.h>

#define SD_READ_RECOVERY_DIAG_MAGIC 0x53524432U

struct sd_read_recovery_metrics {
    uint32_t magic;
    uint32_t multiblock_failures;
    int32_t last_multiblock_error;
    uint32_t fallback_attempts;
    uint32_t fallback_sector_failures;
    int32_t last_fallback_error;
    uint32_t recovered_batches;
    uint32_t last_start_sector;
    uint32_t last_failed_sector;
    uint32_t single_sector_mode;
    uint32_t single_sector_batches;
};

typedef int (*sd_sector_read_fn)(void *context, uint8_t *buffer, uint32_t start_sector, uint32_t sector_count);

/**
 * Read a contiguous batch once, then fall back to checked single-sector reads.
 *
 * The fallback deliberately changes the SD command shape from CMD18/CMD12 to
 * CMD17. It never resets the controller, mutates ring metadata, or accepts the
 * buffer from a failed multi-block transfer as valid.
 */
int sd_read_batch_with_sector_fallback(sd_sector_read_fn read_sectors,
                                       void *context,
                                       uint8_t *buffer,
                                       uint32_t start_sector,
                                       uint32_t sector_count,
                                       uint32_t sector_size,
                                       struct sd_read_recovery_metrics *metrics);

#endif
