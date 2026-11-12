/* Owns the boot/update/storage diagnostics contract and its stable persisted wire format. */
#ifndef OMI_BOOT_TELEMETRY_H
#define OMI_BOOT_TELEMETRY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define OMI_BOOT_RECORD_SIZE 80U
#define OMI_BOOT_SAVE_INTERVAL_MS 600000LL
#define OMI_BOOT_FW_SIZE 16U

enum omi_update_outcome {
    OMI_UPDATE_UNKNOWN = 0,
    OMI_UPDATE_UNCHANGED = 1,
    OMI_UPDATE_UPDATED = 2,
    OMI_UPDATE_NOT_INSTALLED = 3,
};

/* Also the wire flags. Header validity is tracked independently for each boot. */
#define OMI_BOOT_VALID 1U
#define OMI_BOOT_SAFE 2U
#define OMI_BOOT_HEADER_VALID 4U
#define OMI_BOOT_PREVIOUS_HEADER_VALID 8U
#define OMI_BOOT_PREVIOUS_VALID 16U

struct omi_image_identity {
    char fw[OMI_BOOT_FW_SIZE];
    uint8_t header_version[8]; /* major, minor, revision LE16, build LE32 */
};

struct omi_boot_record {
    uint8_t flags;
    uint8_t outcome;
    bool pending_before_boot;
    uint32_t boot_count;
    uint32_t reset_reason;
    uint32_t last_fatal; /* 0 none observed, 1 fatal observed; existing retained signal */
    uint32_t safe_reason;
    uint32_t nor_read_failures;
    uint32_t sd_init_failures;
    struct omi_image_identity current;
    struct omi_image_identity previous;
    bool upload_pending;
};

uint32_t omi_counter_increment(uint32_t value);
enum omi_update_outcome omi_update_classify(const struct omi_boot_record *previous,
                                            const struct omi_image_identity *running,
                                            bool header_valid);
bool omi_boot_save_due(bool dirty, bool attempted, int64_t last_attempt_ms, int64_t now_ms);
/* Stable settings and appended recovery wire format; decode rejects unsupported formats and invalid fields. */
void omi_boot_record_encode(uint8_t out[OMI_BOOT_RECORD_SIZE], const struct omi_boot_record *record);
bool omi_boot_record_decode(struct omi_boot_record *record, const uint8_t *data, size_t len);

/* Thread-context APIs. No flash writes in increment/snapshot paths. */
void omi_boot_telemetry_start(uint32_t reset_reason, bool fatal, bool safe, uint32_t safe_reason);
void omi_boot_telemetry_open(void); /* isolated settings read, once backend access is permitted */
void omi_boot_telemetry_upload_pending(void);
void omi_boot_telemetry_poll(void);
void omi_boot_telemetry_snapshot(struct omi_boot_record *record);
void omi_boot_telemetry_nor_failure(void);
void omi_boot_telemetry_sd_failure(void);

#endif
