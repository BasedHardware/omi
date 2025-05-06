#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/pm/device.h>
#include <zephyr/logging/log.h>

#include "spi_flash.h"

LOG_MODULE_REGISTER(spi_flash, CONFIG_LOG_DEFAULT_LEVEL);

// Get the device pointer for the SPI NOR flash from the device tree
static const struct device *const spi_flash_dev = DEVICE_DT_GET(DT_NODELABEL(spi_flash));

int flash_init(void)
{
    if (!device_is_ready(spi_flash_dev)) {
        LOG_ERR("SPI Flash device (%s) not ready.", spi_flash_dev->name);
        return -ENODEV;
    }
    LOG_INF("SPI Flash control module initialized (Device: %s)", spi_flash_dev->name);
    // Initialization logic can be added here if needed later
    return 0;
}

int flash_off(void)
{
    int ret;

    // if (!device_is_ready(spi_flash_dev)) {
    //     LOG_ERR("SPI Flash device (%s) not ready, cannot suspend.", spi_flash_dev->name);
    //     return -ENODEV;
    // }

    LOG_INF("Suspending SPI Flash device (%s)...", spi_flash_dev->name);
    ret = pm_device_action_run(spi_flash_dev, PM_DEVICE_ACTION_SUSPEND);
    if (ret < 0 && ret != -EALREADY) {
        LOG_ERR("Failed to suspend SPI Flash device (%s): %d", spi_flash_dev->name, ret);
        return ret;
    } else if (ret == -EALREADY) {
        LOG_WRN("SPI Flash device (%s) already suspended.", spi_flash_dev->name);
        return 0;
    }

    LOG_INF("SPI Flash device (%s) suspended successfully.", spi_flash_dev->name);
    return 0;
}
