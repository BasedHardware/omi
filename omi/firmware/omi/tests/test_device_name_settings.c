#include <assert.h>
#include <stdio.h>

#include "settings.inc"

/* The recovery state machine has its own production host harness. */
int safe_mode_settings_set(const char *name, size_t len, settings_read_cb read_cb, void *arg)
{
    (void) name;
    (void) len;
    (void) read_cb;
    (void) arg;
    return -ENOENT;
}

static int save_error;
static int read_result;
static const char *read_bytes;

int settings_subsys_init(void)
{
    return 0;
}
int settings_load_subtree(const char *name)
{
    (void) name;
    return 0;
}
int settings_save_one(const char *name, const void *value, size_t len)
{
    assert(strcmp(name, "omi/device_name") == 0);
    assert(len <= MAX_DEVICE_NAME_PAYLOAD_LEN);
    (void) value;
    return save_error;
}

static int read_name(void *arg, void *destination, size_t len)
{
    (void) arg;
    /* Even a failed callback can dirty its destination. */
    memcpy(destination, read_bytes, len);
    assert(strcmp(app_settings_get_device_name(), "previous") == 0);
    return read_result;
}

int main(void)
{
    assert(app_settings_save_device_name("previous") == 0);
    read_bytes = "abcde";
    const int failures[] = {2, 0, -EIO, 6};
    for (size_t i = 0; i < sizeof(failures) / sizeof(failures[0]); ++i) {
        read_result = failures[i];
        assert(registered_settings_set("device_name", 5, read_name, NULL) < 0);
        assert(strcmp(app_settings_get_device_name(), "previous") == 0);
    }
    read_result = 5;
    read_bytes = "ab\0de";
    assert(registered_settings_set("device_name", 5, read_name, NULL) == -EINVAL);
    assert(strcmp(app_settings_get_device_name(), "previous") == 0);
    assert(registered_settings_set("device_name", MAX_DEVICE_NAME_LEN, read_name, NULL) == -EINVAL);
    read_bytes = "abcde";
    assert(registered_settings_set("device_name", 5, read_name, NULL) == 0);
    assert(strcmp(app_settings_get_device_name(), "abcde") == 0);
    save_error = -ENOSPC;
    assert(app_settings_save_device_name("failed") == -ENOSPC);
    assert(strcmp(app_settings_get_device_name(), "abcde") == 0);
    assert(registered_settings_set("device_name", 0, read_name, NULL) == 0);
    assert(strcmp(app_settings_get_device_name(), "") == 0);
    save_error = 0;
    const char maximum[] = "abcdefghijklmnopqrstuvwxy";
    assert(app_settings_save_device_name(maximum) == 0);
    assert(strcmp(app_settings_get_device_name(), maximum) == 0);
    assert(app_settings_save_device_name("abcdefghijklmnopqrstuvwxyz") == -EINVAL);
    assert(strcmp(app_settings_get_device_name(), maximum) == 0);
    assert(app_settings_save_device_name(NULL) == 0);
    assert(strcmp(app_settings_get_device_name(), "") == 0);
    puts("device name staged NVS load and save tests passed");
}
