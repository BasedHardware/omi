/* Reuse the real settings/NVS owner and its fault-injection regressions. */
#define CONFIG_OMI_ENABLE_OFFLINE_STORAGE 1
#define main run_mute_regressions
#include "test_capture_mute_settings.c"
#undef main
#include "../src/lib/core/features.h"
#include "../src/lib/core/power_control_gatt.h"
static bool storage_paused, off_pending;
static unsigned scheduled;
void sd_write_pause(bool paused)
{
    storage_paused = paused;
}
static bool power_control_off_pending(void)
{
    return off_pending;
}
static int power_control_schedule_off(void)
{
    if (!off_pending)
        scheduled++;
    off_pending = true;
    return 0;
}
int main(void)
{
    assert(run_mute_regressions() == 0);
    const uint8_t active = 0, off = 1, pause = 2, bad = 3;
    assert(OMI_FEATURE_POWER_CONTROL == (1 << 11));
    assert((OMI_FEATURE_POWER_CONTROL & OMI_FEATURE_CAPTURE_MUTE) == 0);
    assert(power_control_gatt_state(false) == active);
    assert(power_control_gatt_write(&pause, 1, 0) == 1);
    assert(capture_mute_is_set() && storage_paused && !capture_mute_should_capture());
    assert(power_control_gatt_state(false) == pause);
    assert(app_settings_init() == 0); /* reboot, or app reconnect, cannot clear pause */
    assert(power_control_gatt_state(false) == pause);
    save_error = -EIO;
    assert(power_control_gatt_write(&active, 1, 0) == BT_GATT_ERR(BT_ATT_ERR_UNLIKELY));
    assert(capture_mute_is_set() && storage_paused);
    save_error = 0;
    /* Old characteristic can resume a pause issued through power control. */
    assert(capture_mute_gatt_write(&active, 1, 0) == 1);
    assert(power_control_gatt_state(false) == active && !storage_paused);
    assert(capture_mute_gatt_write(&off, 1, 0) == 1);
    assert(power_control_gatt_write(&active, 1, 0) == 1);
    assert(!storage_paused && capture_mute_should_capture());
    save_error = -ENOSPC;
    assert(power_control_gatt_write(&pause, 1, 0) == BT_GATT_ERR(BT_ATT_ERR_UNLIKELY));
    assert(capture_mute_is_set() && storage_paused); /* fails closed for this boot (3.0.24) */
    save_error = 0;
    assert(app_settings_init() == 0);
    assert(!capture_mute_is_set()); /* the reported error was honest: not durable */
    capture_mute_apply_runtime();
    unsigned before = writes;
    assert(power_control_gatt_write(&pause, 1, 1) == BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET));
    assert(power_control_gatt_write(&pause, 0, 0) == BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN));
    assert(power_control_gatt_write(&pause, 2, 0) == BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN));
    assert(power_control_gatt_write(&bad, 1, 0) == BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED));
    assert(writes == before);
    assert(power_control_gatt_write(&off, 1, 0) == 1 && scheduled == 1);
    assert(power_control_gatt_write(&off, 1, 0) == 1 && scheduled == 1);
    assert(power_control_gatt_state(false) == off);
    assert(power_control_gatt_write(&active, 1, 0) == BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED));
    assert(power_control_gatt_write(&pause, 1, 0) == BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED));
    assert(writes == before && power_control_gatt_state(true) == off);
    puts("power ATT, persistent pause, shared mute owner, storage gating and shutdown pending passed");
}
