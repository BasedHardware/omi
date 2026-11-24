#include "capture_mute.h"

#include <zephyr/logging/log.h>

#include "settings.h"
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
#include "sd_card.h"
#endif

LOG_MODULE_REGISTER(capture_mute, CONFIG_LOG_DEFAULT_LEVEL);

void capture_mute_apply_runtime(void)
{
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    sd_write_pause(capture_mute_is_set());
#endif
}

int capture_mute_set(bool muted)
{
    int err = app_settings_save_muted(muted ? 1U : 0U);
    if (err) {
        LOG_ERR("Failed to persist mute=%u (err %d)", muted ? 1U : 0U, err);
    } else {
        LOG_INF("Capture mute %s", muted ? "set" : "cleared");
    }
    capture_mute_apply_runtime();
    return err;
}

bool capture_mute_is_set(void)
{
    return app_settings_get_muted() != 0;
}

bool capture_mute_should_capture(void)
{
    /* Issue #5054: muted devices must not store or TX, even when BLE drops. */
    return !capture_mute_is_set();
}
