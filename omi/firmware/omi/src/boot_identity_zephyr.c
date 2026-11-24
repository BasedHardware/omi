#include <string.h>
#include <zephyr/kernel.h>

#include "boot_identity.h"

static uint8_t identity[OMI_BOOT_IDENTITY_SIZE] = {1, OMI_BOOT_IDENTITY_NOT_READY, 1, 0, 0, 0, 0, 0, 0, 0, 1};
static bool prepared;

#if defined(CONFIG_SOC_NRF5340_CPUAPP) && !defined(CONFIG_TRUSTED_EXECUTION_NONSECURE) &&                              \
    !defined(CONFIG_OMI_NATIVE_SIM)
#include <hal/nrf_spu.h>
#include <pm_config.h>
#include <tinycrypt/constants.h>
#include <tinycrypt/sha256.h>
#include <zephyr/device.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/sys/util.h>

BUILD_ASSERT(PM_MCUBOOT_ADDRESS == 0 && PM_MCUBOOT_SIZE == OMI_BOOT_IDENTITY_REGION_SIZE,
             "Loader fingerprint requires the qualified 64 KiB reservation");
BUILD_ASSERT(CONFIG_NRF_SPU_FLASH_REGION_SIZE == 0x4000, "Unexpected nRF5340 SPU geometry");
BUILD_ASSERT(IS_ENABLED(CONFIG_TINYCRYPT_SHA256), "Loader fingerprint requires SHA-256");
static const struct device *const internal_flash = DEVICE_DT_GET(DT_CHOSEN(zephyr_flash_controller));
struct identity_context {
    struct tc_sha256_state_struct hash;
};
static int readable(void *context)
{
    ARG_UNUSED(context);
    if (!device_is_ready(internal_flash)) {
        return -1;
    }
    /* Read permission alone is insufficient: require immutable protection so
     * a concurrent writer cannot change the hash input or revoke access.
     * Never write SPU/NVMC registers or attempt to relax protection. */
    for (unsigned int i = 0; i < OMI_BOOT_IDENTITY_REGION_SIZE / CONFIG_NRF_SPU_FLASH_REGION_SIZE; ++i) {
        uint32_t perm = NRF_SPU_S->FLASHREGION[i].PERM;
        if (!(perm & SPU_FLASHREGION_PERM_READ_Msk) || !(perm & SPU_FLASHREGION_PERM_LOCK_Msk) ||
            (perm & SPU_FLASHREGION_PERM_WRITE_Msk)) {
            return -1;
        }
    }
    return 0;
}
static int begin(void *context)
{
    return tc_sha256_init(&((struct identity_context *) context)->hash) == TC_CRYPTO_SUCCESS ? 0 : -1;
}
static int read_chunk(void *context, uint32_t offset, uint8_t *out, size_t len)
{
    ARG_UNUSED(context);
    return flash_read(internal_flash, offset, out, len);
}
static int update(void *context, const uint8_t *data, size_t len)
{
    return tc_sha256_update(&((struct identity_context *) context)->hash, data, len) == TC_CRYPTO_SUCCESS ? 0 : -1;
}
static int finish(void *context, uint8_t digest[32])
{
    return tc_sha256_final(digest, &((struct identity_context *) context)->hash) == TC_CRYPTO_SUCCESS ? 0 : -1;
}
#endif

void omi_boot_identity_prepare(void)
{
    /* Called synchronously before normal/SAFE GATT registration, never from a
     * GATT callback. Once published, long reads see the same immutable bytes. */
    if (prepared) {
        return;
    }
#if defined(CONFIG_SOC_NRF5340_CPUAPP) && !defined(CONFIG_TRUSTED_EXECUTION_NONSECURE) &&                              \
    !defined(CONFIG_OMI_NATIVE_SIM)
    struct identity_context context;
    const struct omi_boot_identity_ops ops = {readable, begin, read_chunk, update, finish};
    omi_boot_identity_measure(identity, &ops, &context);
#else
    omi_boot_identity_status_packet(identity, OMI_BOOT_IDENTITY_UNSUPPORTED);
#endif
    prepared = true;
}
void omi_boot_identity_snapshot(uint8_t out[OMI_BOOT_IDENTITY_SIZE])
{
    memcpy(out, identity, OMI_BOOT_IDENTITY_SIZE);
}
