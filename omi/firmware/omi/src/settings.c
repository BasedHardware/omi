#include "lib/dk2/settings.h"

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>

LOG_MODULE_REGISTER(app_settings, CONFIG_LOG_DEFAULT_LEVEL);

// Default values if not found in flash
#define DEFAULT_DIM_LIGHT_RATIO 50
#define DEFAULT_MIC_GAIN 6

// In-memory cache for the settings
static uint8_t dim_light_ratio = DEFAULT_DIM_LIGHT_RATIO;
static uint8_t mic_gain = DEFAULT_MIC_GAIN;
static uint32_t storage_offset = 0;
static uint64_t base_timestamp_ms = 0;

static int settings_set(const char *name, size_t len, settings_read_cb read_cb, void *cb_arg)
{
    const char *next;
    int rc;

    if (settings_name_steq(name, "dim_ratio", &next) && !next) {
        if (len != sizeof(dim_light_ratio)) {
            return -EINVAL;
        }
        rc = read_cb(cb_arg, &dim_light_ratio, sizeof(dim_light_ratio));
        if (rc >= 0) {
            LOG_INF("Loaded dim_ratio: %u", dim_light_ratio);
            return 0;
        }
        return rc;
    }

    if (settings_name_steq(name, "mic_gain", &next) && !next) {
        if (len != sizeof(mic_gain)) {
            return -EINVAL;
        }
        rc = read_cb(cb_arg, &mic_gain, sizeof(mic_gain));
        if (rc >= 0) {
            LOG_INF("Loaded mic_gain: %u", mic_gain);
            return 0;
        }
        return rc;
    }

    if (settings_name_steq(name, "storage_offset", &next) && !next) {
        if (len != sizeof(storage_offset)) {
            return -EINVAL;
        }
        rc = read_cb(cb_arg, &storage_offset, sizeof(storage_offset));
        if (rc >= 0) {
            LOG_INF("Loaded storage_offset: %u", storage_offset);
            return 0;
        }
        return rc;
    }

    if (settings_name_steq(name, "base_timestamp", &next) && !next) {
        if (len != sizeof(base_timestamp_ms)) {
            return -EINVAL;
        }
        rc = read_cb(cb_arg, &base_timestamp_ms, sizeof(base_timestamp_ms));
        if (rc >= 0) {
            LOG_INF("Loaded base_timestamp: %llu ms", base_timestamp_ms);
            return 0;
        }
        return rc;
    }

    return -ENOENT;
}

SETTINGS_STATIC_HANDLER_DEFINE(app_settings, "omi", NULL, settings_set, NULL, NULL);

int app_settings_init(void)
{
    int err = settings_subsys_init();
    if (err) {
        LOG_ERR("Failed to initialize settings subsystem (err %d)", err);
        return err;
    }

    err = settings_load();
    if (err) {
        LOG_ERR("Failed to load settings (err %d)", err);
    }

    LOG_INF("Settings initialized. Current dim ratio: %u, mic gain: %u", dim_light_ratio, mic_gain);
    return err;
}

int app_settings_save_dim_ratio(uint8_t new_ratio)
{
    dim_light_ratio = new_ratio;
    int err = settings_save_one("omi/dim_ratio", &dim_light_ratio, sizeof(dim_light_ratio));
    if (err) {
        LOG_ERR("Failed to save dim_ratio (err %d)", err);
    } else {
        LOG_INF("Saved dim_ratio: %u", dim_light_ratio);
    }
    return err;
}

uint8_t app_settings_get_dim_ratio(void)
{
    return dim_light_ratio;
}

int app_settings_save_mic_gain(uint8_t new_gain)
{
    mic_gain = new_gain;
    int err = settings_save_one("omi/mic_gain", &mic_gain, sizeof(mic_gain));
    if (err) {
        LOG_ERR("Failed to save mic_gain (err %d)", err);
    } else {
        LOG_INF("Saved mic_gain: %u", mic_gain);
    }
    return err;
}

uint8_t app_settings_get_mic_gain(void)
{
    return mic_gain;
}

int app_settings_save_storage_offset(uint32_t offset_val)
{
    storage_offset = offset_val;
    int err = settings_save_one("omi/storage_offset", &storage_offset, sizeof(storage_offset));
    if (err) {
        LOG_ERR("Failed to save storage_offset (err %d)", err);
    } else {
        LOG_INF("Saved storage_offset: %u", storage_offset);
    }
    return err;
}

int app_settings_load_storage_offset(uint32_t *offset_val)
{
    if (offset_val == NULL) {
        return -EINVAL;
    }
    *offset_val = storage_offset;
    return 0;
}

int app_settings_save_base_timestamp(uint64_t timestamp_ms)
{
    base_timestamp_ms = timestamp_ms;
    int err = settings_save_one("omi/base_timestamp", &base_timestamp_ms, sizeof(base_timestamp_ms));
    if (err) {
        LOG_ERR("Failed to save base_timestamp (err %d)", err);
    } else {
        LOG_INF("Saved base_timestamp: %llu ms", base_timestamp_ms);
    }
    return err;
}

int app_settings_get_base_timestamp(uint64_t *timestamp_ms)
{
    if (timestamp_ms == NULL) {
        return -EINVAL;
    }
    *timestamp_ms = base_timestamp_ms;
    return 0;
}
