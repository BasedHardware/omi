#include <assert.h>
#include <stdio.h>

#include "../omi/src/wdog_facade.c"

struct device test_wdt = {.ready = true};
static unsigned attempts, installs, setups, feeds;
static int setup_result;
static bool reset_captured;
int hwinfo_get_reset_cause(uint32_t *cause)
{
    assert(attempts == 0);
    *cause = 0x1234;
    return 0;
}
void omi_diagnostics_set_reset_cause(uint32_t cause)
{
    assert(cause == 0x1234 && attempts == 0);
    reset_captured = true;
}
void safe_mode_early_boot(void)
{
    assert(reset_captured);
    attempts++;
}
int wdt_feed(const struct device *dev, int channel)
{
    assert(dev == &test_wdt && channel == 5);
    feeds++;
    return 0;
}
int wdt_install_timeout(const struct device *dev, const struct wdt_timeout_cfg *cfg)
{
    assert(dev == &test_wdt);
    assert(cfg->flags == WDT_FLAG_RESET_SOC && cfg->callback == NULL);
    assert(cfg->window.min == 0 && cfg->window.max == 30000);
    installs++;
    return 5;
}
int wdt_setup(const struct device *dev, uint8_t options)
{
    assert(dev == &test_wdt && options == WDT_OPT_PAUSE_HALTED_BY_DBG);
    setups++;
    return setup_result;
}
int wdt_disable(const struct device *dev)
{
    assert(dev == &test_wdt);
    return -EPERM;
}
int main(void)
{
    watchdog_feed();
    assert(feeds == 0);
    assert(early_watchdog_start() == 0);
    assert(attempts == 1 && installs == 1 && setups == 1);
    assert(watchdog_init() == 0); /* main() feeds, doesn't install twice */
    watchdog_feed();
    assert(installs == 1 && setups == 1 && feeds == 2);
    assert(watchdog_deinit() == -EPERM);
    started = false;
    setup_result = -EIO;
    assert(watchdog_init() == -EIO);
    watchdog_feed();
    assert(feeds == 2); /* failed setup is never treated as running */
    puts("watchdog: early attempt/start, idempotent main init and setup failure passed");
}
