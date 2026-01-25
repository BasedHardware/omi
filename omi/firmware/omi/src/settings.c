#include "lib/core/settings.h"

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
static struct rtc_time rtc_timestamp = {0};
static uint64_t rtc_epoch = 0;

struct lsm6dsl_time_base {
    uint64_t epoch_s;
    uint32_t ts;
    uint32_t reserved;
};

static struct lsm6dsl_time_base lsm6dsl_time_base = {0};

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

    if (settings_name_steq(name, "rtc_timestamp", &next) && !next) {
        if (len != sizeof(rtc_timestamp)) {
            return -EINVAL;
        }
        rc = read_cb(cb_arg, &rtc_timestamp, sizeof(rtc_timestamp));
        if (rc >= 0) {
            LOG_INF("Loaded rtc_timestamp");
            return 0;
        }
        return rc;
    }

    if (settings_name_steq(name, "rtc_epoch", &next) && !next) {
        /* Backward compatibility: older builds may have stored epoch as u32. */
        if (len == sizeof(rtc_epoch)) {
            rc = read_cb(cb_arg, &rtc_epoch, sizeof(rtc_epoch));
            if (rc >= 0) {
                LOG_INF("Loaded rtc_epoch=%llu", rtc_epoch);
                return 0;
            }
            return rc;
        }

        if (len == sizeof(uint32_t)) {
            uint32_t epoch_u32 = 0;
            rc = read_cb(cb_arg, &epoch_u32, sizeof(epoch_u32));
            if (rc >= 0) {
                rtc_epoch = (uint64_t)epoch_u32;
                LOG_INF("Loaded rtc_epoch(u32)=%u -> %llu", epoch_u32, rtc_epoch);
                return 0;
            }
            return rc;
        }

        LOG_WRN("rtc_epoch size mismatch: len=%u expected=%u (or legacy %u)",
            (unsigned)len, (unsigned)sizeof(rtc_epoch), (unsigned)sizeof(uint32_t));
        return -EINVAL;
    }

    if (settings_name_steq(name, "lsm6dsl_time_base", &next) && !next) {
        if (len == sizeof(lsm6dsl_time_base)) {
            rc = read_cb(cb_arg, &lsm6dsl_time_base, sizeof(lsm6dsl_time_base));
            if (rc >= 0) {
                LOG_INF("Loaded lsm6dsl_time_base: epoch_s=%llu ts=0x%08x", lsm6dsl_time_base.epoch_s, lsm6dsl_time_base.ts);
                return 0;
            }
            return rc;
        }

        /* Backward compatibility: older builds may have stored without reserved (12 bytes). */
        if (len == (sizeof(uint64_t) + sizeof(uint32_t))) {
            struct {
                uint64_t epoch_s;
                uint32_t ts;
            } legacy;

            rc = read_cb(cb_arg, &legacy, sizeof(legacy));
            if (rc >= 0) {
                lsm6dsl_time_base.epoch_s = legacy.epoch_s;
                lsm6dsl_time_base.ts = legacy.ts;
                lsm6dsl_time_base.reserved = 0;
                LOG_INF("Loaded lsm6dsl_time_base(legacy): epoch_s=%llu ts=0x%08x", legacy.epoch_s, legacy.ts);
                return 0;
            }
            return rc;
        }

        LOG_WRN("lsm6dsl_time_base size mismatch: len=%u expected=%u (or legacy %u)",
            (unsigned)len, (unsigned)sizeof(lsm6dsl_time_base), (unsigned)(sizeof(uint64_t) + sizeof(uint32_t)));
        return -EINVAL;
    }

    return -ENOENT;
}

int app_settings_save_rtc_timestamp(struct rtc_time ts)
{
    rtc_timestamp = ts;
    int err = settings_save_one("omi/rtc_timestamp", &rtc_timestamp, sizeof(rtc_timestamp));
    if (err) {
        LOG_ERR("Failed to save rtc_timestamp (err %d)", err);
    } else {
        LOG_INF("Saved rtc_timestamp");
    }
    return err;
}

struct rtc_time app_settings_get_rtc_timestamp(void)
{
    return rtc_timestamp;
}

int app_settings_save_rtc_epoch(uint64_t epoch_s)
{
    rtc_epoch = epoch_s;
    int err = settings_save_one("omi/rtc_epoch", &rtc_epoch, sizeof(rtc_epoch));
    if (err) {
        LOG_ERR("Failed to save rtc_epoch (err %d)", err);
    } else {
        LOG_INF("Saved rtc_epoch");
    }
    return err;
}

uint64_t app_settings_get_rtc_epoch(void)
{
    return rtc_epoch;
}

int app_settings_save_lsm6dsl_time_base(uint64_t epoch_s, uint32_t imu_timestamp)
{
    lsm6dsl_time_base.epoch_s = epoch_s;
    lsm6dsl_time_base.ts = imu_timestamp;
    lsm6dsl_time_base.reserved = 0;

    int err = settings_save_one("omi/lsm6dsl_time_base", &lsm6dsl_time_base, sizeof(lsm6dsl_time_base));
    if (err) {
        LOG_ERR("Failed to save lsm6dsl_time_base (err %d)", err);
    } else {
        LOG_INF("Saved lsm6dsl_time_base");
    }
    return err;
}

int app_settings_get_lsm6dsl_time_base(uint64_t *epoch_s, uint32_t *imu_timestamp)
{
    if (epoch_s == NULL || imu_timestamp == NULL) {
        return -EINVAL;
    }
    *epoch_s = lsm6dsl_time_base.epoch_s;
    *imu_timestamp = lsm6dsl_time_base.ts;
    return 0;
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

    LOG_INF("Settings initialized. dim_ratio=%u mic_gain=%u rtc_epoch=%llu lsm6_base_epoch=%llu lsm6_base_ts=0x%08x",
		dim_light_ratio, mic_gain, rtc_epoch, lsm6dsl_time_base.epoch_s, lsm6dsl_time_base.ts);
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
