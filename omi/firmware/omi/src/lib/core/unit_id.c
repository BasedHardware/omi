#include "unit_id.h"

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/drivers/hwinfo.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>

LOG_MODULE_REGISTER(unit_id, CONFIG_LOG_DEFAULT_LEVEL);

#define UNIT_ID_RAW_LEN (UNIT_ID_HEX_LEN / 2)

int unit_id_get(char *out, size_t len)
{
    if (out == NULL || len < UNIT_ID_HEX_LEN + 1) {
        return -EINVAL;
    }

    uint8_t raw[UNIT_ID_RAW_LEN];
    ssize_t read = hwinfo_get_device_id(raw, sizeof(raw));
    if (read < 0) {
        return (int) read;
    }
    if (read != sizeof(raw)) {
        return -EIO;
    }

    for (size_t i = 0; i < sizeof(raw); i++) {
        snprintf(&out[i * 2], 3, "%02X", raw[i]);
    }
    out[UNIT_ID_HEX_LEN] = '\0';
    return 0;
}

int unit_id_publish(void)
{
    char id[UNIT_ID_HEX_LEN + 1];
    int err = unit_id_get(id, sizeof(id));
    if (err) {
        LOG_ERR("Failed to read unit ID (err %d)", err);
        printk("UNIT_ID: unavailable (err=%d)\n", err);
        return err;
    }

    // Production-line helper: fixtures parse this line to key the lot roster.
    printk("UNIT_ID: %s\n", id);

    err = settings_runtime_set("bt/dis/serial", id, strlen(id));
    if (err) {
        LOG_ERR("Failed to set DIS serial number (err %d)", err);
        return err;
    }

    LOG_INF("Unit ID %s published as DIS serial number", id);
    return 0;
}
