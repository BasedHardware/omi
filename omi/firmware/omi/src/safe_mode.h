#ifndef OMI_SAFE_MODE_H
#define OMI_SAFE_MODE_H

#include <stdbool.h>
#include <stdint.h>
#include <zephyr/settings/settings.h>

/* PRE_KERNEL_2 records the attempt; main selects SAFE before app settings/devices. */
void safe_mode_early_boot(void);
bool safe_mode_boot(void);
void safe_mode_restore(void);
void safe_mode_persist(void);
int safe_mode_devices_init(void);
void safe_mode_sd_bus_init(void);
int safe_mode_settings_set(const char *name, size_t len, settings_read_cb read_cb, void *arg);
void safe_mode_settings_ready(int status);
bool safe_mode_active(void);
void safe_mode_main_loop_ready(bool advertising);
void safe_mode_poll(void);
void safe_mode_run(void);

struct safe_mode_snapshot {
    uint32_t boot_count;
    uint32_t reset_reason;
    uint32_t latch_reason; /* 0 none, 1 crash loop, 2 button, 3 simulation */
    bool active;
    bool latched;
    uint8_t bootstate; /* 0 unknown, 1 SAFE, 2 GOOD, 3 DFU trial */
};
void safe_mode_snapshot_get(struct safe_mode_snapshot *out);
uint32_t safe_mode_total_boots(void);
uint32_t safe_mode_restore_total_boots(uint32_t persisted_count);
#endif
