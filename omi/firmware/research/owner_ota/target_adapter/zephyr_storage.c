/* Compiled only by isolated research build; never included by production. */
#include <arm_cmse.h>
#include <errno.h>
#include <soc.h>
#include <zephyr/device.h>
#include <zephyr/drivers/flash.h>

#include "storage_adapter.h"
#define NOR DT_NODELABEL(spi_flash)
_Static_assert(DT_REG_ADDR(DT_BUS(NOR)) == NRF_SPIM3_S_BASE, "Secure SPI3 required");
_Static_assert(DT_PROP(NOR, size) / 8 == 0x200000u, "2 MiB NOR required");
_Static_assert((NRF_SPIM3_S_BASE & 0xffffu) / 0x1000u == 12u, "SPU SPI3 ID");
_Static_assert(offsetof(NRF_SPU_Type, PERIPHID) == 0x800u, "SPU layout");
_Static_assert(SPU_PERIPHID_PERM_SECATTR_Msk == 0x10u, "SPU SECATTR");
_Static_assert(SPU_PERIPHID_PERM_DMASEC_Msk == 0x20u, "SPU DMASEC");
_Static_assert(SPU_PERIPHID_PERM_LOCK_Msk == 0x100u, "SPU lock");
_Static_assert(0x54000u % 0x4000u == 0 && 0xf0000u % 0x4000u == 0, "16KiB flash boundary");
_Static_assert(0x20012000u % 0x2000u == 0, "8KiB RAM boundary");
/* No register writes. Even these readbacks are never invoked by research main.
 * SPI3 also carries SD. Owning peripheral alone is insufficient: pin protection,
 * all shared driver users, DMA memory, debug/master paths and reset epoch remain
 * unqualified. Therefore this predicate MUST NOT return ready on these bits. */
static __attribute__((used)) int target_owned(void *unused)
{
    (void) unused;
    volatile uint32_t spi = NRF_SPU_S->PERIPHID[12].PERM;
    volatile uint32_t pins0 = NRF_SPU_S->GPIOPORT[0].PERM;
    volatile uint32_t pins1 = NRF_SPU_S->GPIOPORT[1].PERM;
    (void) spi;
    (void) pins0;
    (void) pins1;
    return 0;
}
/* Private trusted hook, never caller supplied. No write/erase branch exists.
 * flash_read returns 0 on complete success; Zephyr exposes no partial count.
 * Error poisons lease; higher-level authenticated digest catches corrupt reads.
 * Secure bounce placement must be verified before a future activation. */
static __attribute__((used)) int target_read(void *unused, unsigned op, uint32_t off, void *p, size_t n)
{
    (void) unused;
    uintptr_t ptr = (uintptr_t) p;
    if (!n || n > CV1_BOUNCE || ptr % 32 || ptr < 0x20002000u || ptr > 0x20012000u - n ||
        !cmse_check_address_range(p, n, CMSE_MPU_READWRITE))
        return -EACCES;
    /* TT reports attribution, unlike MPU access permission alone. Check every
     * 32-byte attribution granule touched by the aligned <=256-byte bounce.
     * This is still a snapshot: exclusive locked ownership is NOT established. */
    for (size_t i = 0; i < n; i += 32) {
        if (!cmse_TT((void *) (ptr + i)).flags.secure)
            return -EACCES;
    }
    if (op || off < 0x130000u || n > CV1_BOUNCE || off > 0x1f0000u - n)
        return -EACCES;
    const struct device *dev = DEVICE_DT_GET(NOR);
    if (!device_is_ready(dev))
        return -ENODEV;
    return flash_read(dev, (off_t) off, p, n) == 0 ? (int) n : -EIO;
}
int cv1_target_storage_init(struct cv1_storage *s)
{
    /* No hidden simulation, no invented reset epoch, no target I/O. */
    (void) s;
    (void) target_owned;
    (void) target_read;
    return -ENOTSUP;
}
