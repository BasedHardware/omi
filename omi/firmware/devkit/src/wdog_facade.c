#include <zephyr/drivers/watchdog.h>
#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>

LOG_MODULE_REGISTER(wdog_facade, CONFIG_LOG_DEFAULT_LEVEL);

#define WATCHDOG_TIMEOUT_MS 30000U  // 30 seconds

static const struct device *wdt_dev;
static int wdt_channel_id;

void watchdog_feed(void)
{
    if (wdt_dev && device_is_ready(wdt_dev)) {
        wdt_feed(wdt_dev, wdt_channel_id);
    }
}

int watchdog_init(void)
{
    int ret;
    struct wdt_timeout_cfg wdt_config;

    // Get watchdog device (nRF52840 uses wdt0 label)
    wdt_dev = DEVICE_DT_GET(DT_NODELABEL(wdt0));
    if (!device_is_ready(wdt_dev)) {
        LOG_ERR("Watchdog device not ready");
        return -ENODEV;
    }

    // Configure watchdog timeout
    wdt_config.flags = WDT_FLAG_RESET_SOC;         // Reset entire SoC on timeout
    wdt_config.window.min = 0U;                    // No minimum window
    wdt_config.window.max = WATCHDOG_TIMEOUT_MS;   // 30 seconds timeout
    wdt_config.callback = NULL;                    // No callback, just reset

    // Install watchdog timeout
    wdt_channel_id = wdt_install_timeout(wdt_dev, &wdt_config);
    if (wdt_channel_id < 0) {
        LOG_ERR("Watchdog install failed: %d", wdt_channel_id);
        return wdt_channel_id;
    }

    // Start watchdog
    ret = wdt_setup(wdt_dev, WDT_OPT_PAUSE_HALTED_BY_DBG);
    if (ret < 0) {
        LOG_ERR("Watchdog setup failed: %d", ret);
        return ret;
    }

    LOG_INF("Watchdog initialized (timeout: 30s, channel: %d)", wdt_channel_id);
    return 0;
}

int watchdog_deinit(void)
{
    return wdt_disable(wdt_dev);
}

