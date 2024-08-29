#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include "utils.h"

static uint8_t settings_enable = 0;

static int settings_set(const char *name, size_t len, settings_read_cb read_cb, void *cb_arg)
{
    const char *next;
    if (settings_name_steq(name, "enable", &next) && !next)
    {
        if (len != sizeof(settings_enable))
        {
            return -EINVAL;
        }
        return read_cb(cb_arg, &settings_enable, sizeof(settings_enable));
    }
    return -ENOENT;
}

static struct settings_handler cfg = {
    .name = "main",
    .h_set = settings_set,
};

int settings_start()
{
    ASSERT_OK(settings_subsys_init());
    ASSERT_OK(settings_register(&cfg));
    ASSERT_OK(settings_load());
}

bool settings_read_enable()
{
    return settings_enable != 0;
}

int settings_write_enable(bool enable)
{
    uint8_t v = enable ? 1 : 0;
    if (settings_enable != v)
    {
        settings_enable = v;
        ASSERT_OK(settings_save_one("main/enable", &settings_enable, sizeof(settings_enable)));
    }
}