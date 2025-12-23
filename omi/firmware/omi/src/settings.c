#include "settings.h"

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>
#include <string.h>

LOG_MODULE_REGISTER(app_settings, CONFIG_LOG_DEFAULT_LEVEL);

// Default values if not found in flash
#define DEFAULT_DIM_LIGHT_RATIO 50
#define DEFAULT_MIC_GAIN 6
#define DEFAULT_DEVICE_NAME "Omi"

// In-memory cache for the settings
static uint8_t dim_light_ratio = DEFAULT_DIM_LIGHT_RATIO;
static uint8_t mic_gain = DEFAULT_MIC_GAIN;
static char device_name[33] = DEFAULT_DEVICE_NAME; // 32 chars + null terminator

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

    // New Handle loading device name
    if (settings_name_steq(name, "device_name", &next) && !next) {
        if (len > sizeof(device_name) - 1) {
            return -EINVAL;
        }
        rc = read_cb(cb_arg, device_name, len);
        if (rc >= 0) {
            device_name[rc] = '\0'; // Ensure null termination
            LOG_INF("Loaded device_name: %s", device_name);
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

    LOG_INF("Settings initialized. Dim: %u, Gain: %u, Name: %s", dim_light_ratio, mic_gain, device_name);
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

// New Save Device Name
int app_settings_save_device_name(const char *name, size_t len)
{
    if (len >= sizeof(device_name)) {
        return -EINVAL;
    }
    memcpy(device_name, name, len);
    device_name[len] = '\0';
    
    int err = settings_save_one("omi/device_name", device_name, len);
    if (err) {
        LOG_ERR("Failed to save device_name (err %d)", err);
    } else {
        LOG_INF("Saved device_name: %s", device_name);
    }
    return err;
}

// New Get Device Name
const char* app_settings_get_device_name(void)
{
    return device_name;
}