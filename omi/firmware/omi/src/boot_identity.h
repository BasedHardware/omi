#ifndef OMI_BOOT_IDENTITY_H
#define OMI_BOOT_IDENTITY_H
#include <stddef.h>
#include <stdint.h>
#define OMI_BOOT_IDENTITY_SIZE 44U
#define OMI_BOOT_IDENTITY_REGION_SIZE 65536U
#define OMI_BOOT_IDENTITY_CHUNK_SIZE 256U
enum omi_boot_identity_status {
    OMI_BOOT_IDENTITY_UNSUPPORTED = 0,
    OMI_BOOT_IDENTITY_OK = 1,
    OMI_BOOT_IDENTITY_UNREADABLE = 2,
    OMI_BOOT_IDENTITY_ERROR = 3,
    OMI_BOOT_IDENTITY_NOT_READY = 4,
};
/* Internal callbacks only. No caller-supplied address/range is exposed over BLE.
 * readable must establish safe access BEFORE any read. read must fill all bytes.
 * Hash callbacks return zero on success. The digest is published only at end. */
struct omi_boot_identity_ops {
    int (*readable)(void *context);
    int (*begin)(void *context);
    int (*read)(void *context, uint32_t offset, uint8_t *out, size_t len);
    int (*update)(void *context, const uint8_t *data, size_t len);
    int (*finish)(void *context, uint8_t digest[32]);
};
void omi_boot_identity_status_packet(uint8_t out[OMI_BOOT_IDENTITY_SIZE], enum omi_boot_identity_status status);
void omi_boot_identity_measure(uint8_t out[OMI_BOOT_IDENTITY_SIZE],
                               const struct omi_boot_identity_ops *ops,
                               void *context);
/* Zephyr adapter: prepare once before BLE starts; snapshot is immutable afterward. */
void omi_boot_identity_prepare(void);
void omi_boot_identity_snapshot(uint8_t out[OMI_BOOT_IDENTITY_SIZE]);
#endif
