#ifndef TEST_WATCHDOG_H
#define TEST_WATCHDOG_H
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
struct device {
    bool ready;
};
extern struct device test_wdt;
#define DEVICE_DT_GET(x) (&test_wdt)
#define DT_NODELABEL(x) 0
#define WDT_FLAG_RESET_SOC 1
#define WDT_OPT_PAUSE_HALTED_BY_DBG 2
struct wdt_timeout_cfg {
    uint8_t flags;
    struct {
        uint32_t min;
        uint32_t max;
    } window;
    void *callback;
};
static inline bool device_is_ready(const struct device *dev)
{
    return dev->ready;
}
int wdt_feed(const struct device *, int);
int wdt_install_timeout(const struct device *, const struct wdt_timeout_cfg *);
int wdt_setup(const struct device *, uint8_t);
int wdt_disable(const struct device *);
#endif
