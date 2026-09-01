#include "startup.h"

#include <stdbool.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "sdcard.h"
#include "storage.h"
#include "transport.h"

LOG_MODULE_REGISTER(startup, CONFIG_LOG_DEFAULT_LEVEL);

static bool offline_storage_available;

void startup_init_optional_storage(void)
{
    offline_storage_available = false;

    LOG_INF("Mounting SD card");
    int err = mount_sd_card();
    if (err) {
        LOG_WRN("SD mount failed (err %d); continuing without offline storage", err);
        return;
    }

    k_msleep(500);

    LOG_INF("Initializing offline storage");
    err = storage_init();
    if (err) {
        LOG_WRN("Offline storage init failed (err %d); continuing without offline storage", err);
        return;
    }

    offline_storage_available = true;
}

int startup_start_transport(void)
{
    return transport_start(offline_storage_available);
}
