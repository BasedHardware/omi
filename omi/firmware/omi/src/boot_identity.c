#include "boot_identity.h"

#include <string.h>
void omi_boot_identity_status_packet(uint8_t out[OMI_BOOT_IDENTITY_SIZE], enum omi_boot_identity_status status)
{
    memset(out, 0, OMI_BOOT_IDENTITY_SIZE);
    out[0] = 1; /* schema */
    out[1] = (uint8_t) status;
    out[2] = 1;  /* SHA-256 */
    out[10] = 1; /* region length 0x00010000 LE; start is zero */
}
void omi_boot_identity_measure(uint8_t out[OMI_BOOT_IDENTITY_SIZE],
                               const struct omi_boot_identity_ops *ops,
                               void *context)
{
    uint8_t chunk[OMI_BOOT_IDENTITY_CHUNK_SIZE];
    uint8_t digest[32] = {0};
    omi_boot_identity_status_packet(out, OMI_BOOT_IDENTITY_ERROR);
    if (!ops || !ops->readable || !ops->begin || !ops->read || !ops->update || !ops->finish) {
        return;
    }
    if (ops->readable(context) != 0) {
        omi_boot_identity_status_packet(out, OMI_BOOT_IDENTITY_UNREADABLE);
        return;
    }
    if (ops->begin(context) != 0) {
        return;
    }
    for (uint32_t offset = 0; offset < OMI_BOOT_IDENTITY_REGION_SIZE; offset += sizeof(chunk)) {
        /* This is the internal flash adapter, not untrusted peripheral DMA. */
        memset(chunk, 0, sizeof(chunk));
        if (ops->read(context, offset, chunk, sizeof(chunk)) != 0 || ops->update(context, chunk, sizeof(chunk)) != 0) {
            return;
        }
    }
    if (ops->finish(context, digest) != 0) {
        return;
    }
    memcpy(out + 12, digest, sizeof(digest));
    out[1] = OMI_BOOT_IDENTITY_OK;
}
