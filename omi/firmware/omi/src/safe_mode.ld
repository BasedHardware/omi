/* Keep PM geometry unchanged; explicitly own a NOLOAD slice within app SRAM.
 * App stacks/heaps are static allocations in data/bss/noinit. Fail the link
 * rather than silently overlapping them or moving the low-RAM RTT block.
 */
#include <zephyr/devicetree.h>
#define SAFE_RAM DT_REG_ADDR(DT_NODELABEL(safe_mode_ram))
ASSERT(__data_region_end <= SAFE_RAM, "data overlaps safe-mode retained RAM")
ASSERT(__bss_end <= SAFE_RAM, "bss overlaps safe-mode retained RAM")
ASSERT(ADDR(noinit) + SIZEOF(noinit) <= SAFE_RAM, "noinit overlaps safe-mode retained RAM")
.omi_retained SAFE_RAM (NOLOAD) :
{
    KEEP(*(.omi_retained))
} > RAM
ASSERT(SIZEOF(.omi_retained) <= DT_REG_SIZE(DT_NODELABEL(safe_mode_ram)), "safe-mode record too big")
