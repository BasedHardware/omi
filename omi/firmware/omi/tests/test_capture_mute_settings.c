/* Execute the production NVS owner and ATT contract with a faultable store. */
#include <assert.h>
#include <stdio.h>

#include "../src/lib/core/capture_mute.c"
#include "../src/lib/core/capture_mute_gatt.h"
#include "../src/settings.c"

/* The recovery state machine has its own production host harness. */
int safe_mode_settings_set(const char *name, size_t len, settings_read_cb read_cb, void *arg)
{
    (void) name;
    (void) len;
    (void) read_cb;
    (void) arg;
    return -ENOENT;
}

static uint8_t persisted;
static int save_error;
static unsigned writes;
static size_t stored_len = 1;
static int read_result = 1;
static int init_error;
static int load_error;
static bool stored = true;

static int read_muted(void *arg, void *destination, size_t length)
{
    (void) arg;
    assert(length == 1);
    if (read_result != 1)
        return read_result;
    memcpy(destination, &persisted, length);
    return (int) length;
}

int settings_subsys_init(void)
{
    return init_error;
}

int settings_load_subtree(const char *name)
{
    assert(strcmp(name, "omi") == 0);
    if (load_error) {
        return load_error;
    }
    return stored ? registered_settings_set("muted", stored_len, read_muted, NULL) : 0;
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
    /* Before settings load, and for a fresh device with no stored value. */
    assert(capture_mute_is_set());
    stored = false;
    assert(app_settings_init() == 0);
    assert(capture_mute_should_capture());
    stored = true;
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
    assert(!capture_mute_should_capture()); /* the app asked to stop: fail closed now */
    assert(app_settings_init() == 0);
    assert(!capture_mute_is_set()); /* ... but the error told the app it is not durable */

    /* A muted pendant whose settings backend fails at boot stays muted. */
    save_error = 0;
    assert(capture_mute_gatt_write(&pause, 1, 0) == 1);
    init_error = -EIO;
    assert(app_settings_init() == -EIO);
    assert(capture_mute_is_set());
    init_error = 0;
    load_error = -EIO;
    assert(app_settings_init() == -EIO);
    assert(capture_mute_is_set());
    /* Even an unmuted pendant fails closed when the stored state is unknown. */
    load_error = 0;
    assert(capture_mute_gatt_write(&resume, 1, 0) == 1);
    load_error = -EIO;
    assert(app_settings_init() == -EIO);
    assert(capture_mute_is_set());
    load_error = 0;
    assert(app_settings_init() == 0);
    assert(capture_mute_should_capture());
    save_error = -ENOSPC;

    /* An unreadable stored mute may be a user's pause: it must not resume capture. */
    stored_len = 2;
    assert(app_settings_init() != 0);
    assert(capture_mute_is_set());
    stored_len = 1;
    assert(capture_mute_gatt_write(&resume, 1, 0) == BT_GATT_ERR(BT_ATT_ERR_UNLIKELY));
    save_error = 0;
    assert(capture_mute_gatt_write(&resume, 1, 0) == 1);
    assert(capture_mute_should_capture());
    read_result = -EIO;
    assert(app_settings_init() != 0);
    assert(capture_mute_is_set());
    read_result = 0;
    assert(app_settings_init() != 0);
    assert(capture_mute_is_set());
    read_result = 1;
    assert(app_settings_init() == 0);
    assert(capture_mute_should_capture());

    const unsigned before = writes;
    assert(capture_mute_gatt_write(&pause, 1, 1) == BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET));
    assert(capture_mute_gatt_write(&pause, 0, 0) == BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN));
    assert(writes == before);
    puts("capture mute durability and ATT failure tests passed");
    return 0;
}
