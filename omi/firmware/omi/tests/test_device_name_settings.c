/* Exercise the production settings loader with a deterministic NVS boundary. */
#include <assert.h>
#include <stdio.h>

#include "../src/settings.c"

struct stored_value {
    const void *bytes;
    size_t length;
    int read_result;
};

static struct stored_value name_record;
static unsigned writes;

static int read_value(void *arg, void *destination, size_t length)
{
    const struct stored_value *value = arg;
    if (value->read_result < 0) {
        return value->read_result;
    }
    size_t available = (size_t) value->read_result;
    if (available > length) {
        available = length;
    }
    memcpy(destination, value->bytes, available);
    return value->read_result;
}

int settings_subsys_init(void)
{
    return 0;
}

int settings_load_subtree(const char *name)
{
    assert(strcmp(name, "omi") == 0);
    uint8_t saved_dim = 77;
    struct stored_value dim_record = {&saved_dim, sizeof(saved_dim), sizeof(saved_dim)};
    int err = registered_settings_set("dim_ratio", dim_record.length, read_value, &dim_record);
    assert(err == 0);
    return registered_settings_set("dev_name", name_record.length, read_value, &name_record);
}

int settings_save_one(const char *name, const void *value, size_t len)
{
    (void) name;
    (void) value;
    (void) len;
    writes++;
    return 0;
}

int settings_delete(const char *name)
{
    (void) name;
    return 0;
}

static void check_invalid_name(const void *bytes, size_t length, int read_result)
{
    assert(app_settings_save_device_name("Previous", 8) == 0);
    writes = 0;
    struct stored_value invalid_record = {bytes, length, read_result};
    name_record = invalid_record;
    assert(app_settings_init() == 0);
    assert(strcmp(app_settings_get_device_name(), CONFIG_BT_DEVICE_NAME) == 0);
    assert(app_settings_get_dim_ratio() == 77);
    assert(writes == 0);
}

int main(void)
{
    const uint8_t malformed[] = {0xe0, 0x80, 0x80};
    check_invalid_name("", 0, 0);
    check_invalid_name("012345678901234567890", 21, 21);
    check_invalid_name(malformed, sizeof(malformed), sizeof(malformed));
    check_invalid_name("Omi", 3, 1);

    struct stored_value valid_record = {"Kitchen Omi", 11, 11};
    name_record = valid_record;
    assert(app_settings_init() == 0);
    assert(strcmp(app_settings_get_device_name(), "Kitchen Omi") == 0);

    name_record.read_result = -EIO;
    assert(app_settings_init() == -EIO);
    puts("device-name settings loader tests passed");
    return 0;
}
