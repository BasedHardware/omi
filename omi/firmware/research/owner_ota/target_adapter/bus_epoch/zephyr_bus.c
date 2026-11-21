/* Research-only real API compilation, never called by target initializer. */
#include <arm_cmse.h>
#include <soc.h>
#include <zephyr/device.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/storage/disk_access.h>

#include "secure_bus.h"
#define NOR DT_NODELABEL(spi_flash)
#define SPI DT_BUS(NOR)
_Static_assert(DT_REG_ADDR(SPI) == NRF_SPIM3_S_BASE, "Secure shared SPI3");
_Static_assert(DT_SPI_DEV_CS_GPIOS_PIN(NOR) == 11, "NOR CS P0.11");
_Static_assert(DT_GPIO_PIN_BY_IDX(SPI, cs_gpios, 0) == 11, "SD CS P1.11");
static const struct gpio_dt_spec nor_cs = GPIO_DT_SPEC_GET_BY_IDX(SPI, cs_gpios, 1);
static const struct gpio_dt_spec sd_cs = GPIO_DT_SPEC_GET_BY_IDX(SPI, cs_gpios, 0);
/* Only a whole-driver read: SD driver retains its exact config and completes its
 * own spi_release. There is no raw transaction, arbitrary LBA or writing entry. */
__attribute__((used)) static int whole_read(void *ctx, enum cv1_bus_service op, uint32_t off, void *dst, size_t n)
{
    (void) ctx;
    uintptr_t ptr = (uintptr_t) dst;
    if (!n || n > 512 || ptr % 32 || ptr < 0x20002000u || ptr > 0x20012000u - n ||
        !cmse_check_address_range(dst, n, CMSE_MPU_READWRITE))
        return -1;
    for (size_t i = 0; i < n; i += 32)
        if (!cmse_TT((void *) (ptr + i)).flags.secure)
            return -1;
    if (op == CV1_BUS_NOR_READ && n && n <= 512 &&
        ((off >= 0x130000 && off <= 0x190000 - n) || (off >= 0x190000 && off <= 0x1f0000 - n))) {
        const struct device *dev = DEVICE_DT_GET(NOR);
        return device_is_ready(dev) && flash_read(dev, off, dst, n) == 0 ? (int) n : -1;
    }
    if (op == CV1_BUS_SD_SECTOR_ZERO && off == 0 && n == 512)
        return disk_access_read("SD", dst, 0, 1) == 0 ? 512 : -1;
    return -1;
}
__attribute__((used)) static int finish(void *ctx)
{
    (void) ctx;
    /* Read-only observations; do not force CS or abort another driver's transfer.
     * get_dt logical 0 == deasserted for the active-low CS pins. */
    if (!gpio_is_ready_dt(&nor_cs) || !gpio_is_ready_dt(&sd_cs) || gpio_pin_get_dt(&nor_cs) != 0 ||
        gpio_pin_get_dt(&sd_cs) != 0)
        return -1;
    /* GPIO levels alone do not prove DMA stopped or SPI lock released. No public
     * high-level API exports those facts for both drivers. Until a fixed driver
     * ownership hook exists, refusing here is mandatory, never fake success. */
    return -1;
}
