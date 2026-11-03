#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/kernel.h>

#include "safe_mode.h"

#ifdef CONFIG_OMI_FAULT_INJECT_DRIVER_HANG
/* A real deferred device: device_init() invokes the hang, not a latch-aware
 * SYS_INIT hook. The recovery path never calls device_init() on this object.
 */
static int fault_init(const struct device *dev)
{
    ARG_UNUSED(dev);
    printk("FAULT_INJECT: driver init hang\n");
    for (;;) {}
    return 0;
}
DEVICE_DT_DEFINE(DT_NODELABEL(safe_mode_fault),
                 fault_init,
                 NULL,
                 NULL,
                 NULL,
                 POST_KERNEL,
                 CONFIG_KERNEL_INIT_PRIORITY_DEVICE,
                 NULL);
#endif

/* Bus before children. SPI3/NOR, GPIO, PWM and BLE dependencies remain eager.
 * Match app.overlay; disabled drivers have no device object to reference.
 */
static const struct device *const deferred[] = {
#ifdef CONFIG_OMI_FAULT_INJECT_DRIVER_HANG
    DEVICE_DT_GET(DT_NODELABEL(safe_mode_fault)),
#endif
#if defined(CONFIG_I2C) && DT_NODE_HAS_STATUS(DT_NODELABEL(i2c2), okay)
    DEVICE_DT_GET(DT_NODELABEL(i2c2)),
#endif
#if defined(CONFIG_AUDIO_DMIC_NRFX_PDM) && DT_NODE_HAS_STATUS(DT_NODELABEL(pdm0), okay)
    DEVICE_DT_GET(DT_NODELABEL(pdm0)),
#endif
#if defined(CONFIG_I2S_NRFX) && DT_NODE_HAS_STATUS(DT_NODELABEL(i2s0), okay)
    DEVICE_DT_GET(DT_NODELABEL(i2s0)),
#endif
#if defined(CONFIG_ADC_NRFX_SAADC) && DT_NODE_HAS_STATUS(DT_NODELABEL(adc), okay)
    DEVICE_DT_GET(DT_NODELABEL(adc)),
#endif
#if defined(CONFIG_LSM6DSL) && DT_NODE_HAS_STATUS(DT_NODELABEL(lsm6ds3tr_c), okay)
    DEVICE_DT_GET(DT_NODELABEL(lsm6ds3tr_c)),
#endif
#if (defined(CONFIG_SPI_SDHC) || defined(CONFIG_OMI_SDHC_SPI_CMD12_FIX)) &&                                            \
    DT_NODE_HAS_STATUS(DT_NODELABEL(sdhc0), okay)
    DEVICE_DT_GET(DT_NODELABEL(sdhc0)),
#endif
#if defined(CONFIG_DISK_DRIVER_SDMMC) && DT_NODE_HAS_STATUS(DT_CHILD(DT_NODELABEL(sdhc0), mmc), okay)
    DEVICE_DT_GET(DT_CHILD(DT_NODELABEL(sdhc0), mmc)),
#endif
    NULL,
};

int safe_mode_devices_init(void)
{
    for (size_t i = 0; deferred[i] != NULL; ++i) {
        int err = device_init(deferred[i]);
        if (err) {
            printk("Deferred device %s failed (%d)\n", deferred[i]->name, err);
            return err;
        }
    }
    return 0;
}
