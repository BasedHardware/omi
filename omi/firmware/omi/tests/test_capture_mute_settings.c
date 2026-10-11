/* Execute the production NVS owner and ATT contract with a faultable store. */
#include <assert.h>
#include <stdio.h>

#include "../src/lib/core/capture_mute.c"
#include "../src/lib/core/capture_mute_gatt.h"
#include "../src/settings.c"

static uint8_t persisted;
static int save_error;
static unsigned writes;

static int read_muted(void *arg, void *destination, size_t length)
{
    (void) arg;
    assert(length == 1);
    memcpy(destination, &persisted, length);
    return (int) length;
}

int settings_subsys_init(void)
{
    return 0;
}

int settings_load_subtree(const char *name)
{
    assert(strcmp(name, "omi") == 0);
    return registered_settings_set("muted", 1, read_muted, NULL);
}

int settings_save_one(const char *name, const void *value, size_t len)
{
    assert(strcmp(name, "omi/muted") == 0);
    assert(len == 1);
    writes++;
    if (save_error)
        return save_error;
    persisted = *(const uint8_t *) value;
    return 0;
}

int main(void)
{
    const uint8_t pause = 1, resume = 0;
    assert(app_settings_init() == 0);
    assert(capture_mute_should_capture());
    assert(capture_mute_gatt_write(&pause, 1, 0) == 1);
    assert(!capture_mute_should_capture());
    assert(app_settings_init() == 0); /* reboot/reload preserves mute */
    assert(capture_mute_is_set());

    save_error = -EIO;
    assert(capture_mute_gatt_write(&resume, 1, 0) == BT_GATT_ERR(BT_ATT_ERR_UNLIKELY));
    assert(capture_mute_is_set()); /* failed unmute cannot open capture */
    assert(app_settings_init() == 0);
    assert(capture_mute_is_set());

    save_error = 0;
    assert(capture_mute_gatt_write(&resume, 1, 0) == 1);
    assert(capture_mute_should_capture());
    save_error = -ENOSPC;
    assert(capture_mute_gatt_write(&pause, 1, 0) == BT_GATT_ERR(BT_ATT_ERR_UNLIKELY));
    assert(!capture_mute_is_set()); /* failure cannot masquerade as durable mute */
    assert(app_settings_init() == 0);
    assert(!capture_mute_is_set());

    const unsigned before = writes;
    assert(capture_mute_gatt_write(&pause, 1, 1) == BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET));
    assert(capture_mute_gatt_write(&pause, 0, 0) == BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN));
    assert(writes == before);
    puts("capture mute durability and ATT failure tests passed");
    return 0;
}
