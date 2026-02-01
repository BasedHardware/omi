#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>

#include <errno.h>
#include <stdio.h>

#include "rtc.h"
#include "lib/core/settings.h"

LOG_MODULE_REGISTER(rtc, CONFIG_LOG_DEFAULT_LEVEL);

static uint64_t base_epoch_ms;
static int64_t base_uptime_ms;
static bool utc_valid;

static struct k_mutex rtc_lock;

// Debug functions to format UTC datetime strings
#ifdef CONFIG_LOG
static void civil_from_days(int64_t z_days, int32_t *year, uint8_t *month, uint8_t *day)
{
    /*
     * Howard Hinnant's algorithm: convert days since 1970-01-01 into Y-M-D.
     * Works for a wide range of dates with only integer math.
     */
    int64_t z = z_days + 719468;
    int64_t era = (z >= 0) ? (z / 146097) : ((z - 146096) / 146097);
    uint32_t doe = (uint32_t)(z - era * 146097);
    uint32_t yoe = (doe - doe / 1460U + doe / 36524U - doe / 146096U) / 365U;
    int32_t y = (int32_t)yoe + (int32_t)era * 400;
    uint32_t doy = doe - (365U * yoe + yoe / 4U - yoe / 100U);
    uint32_t mp = (5U * doy + 2U) / 153U;
    uint32_t d = doy - (153U * mp + 2U) / 5U + 1U;
    uint32_t m = mp + ((mp < 10U) ? 3U : (uint32_t)-9);
    y += (m <= 2U);

    *year = y;
    *month = (uint8_t)m;
    *day = (uint8_t)d;
}

static int rtc_format_utc_datetime(int64_t utc_epoch_s, char *out, size_t out_len)
{
    if (out == NULL) {
        return -EINVAL;
    }
    if (out_len < RTC_UTC_DATETIME_STRLEN) {
        out[0] = '\0';
        return -ENOSPC;
    }
    if (utc_epoch_s < 0) {
        out[0] = '\0';
        return -EINVAL;
    }

    int64_t days = utc_epoch_s / 86400;
    int64_t sod = utc_epoch_s % 86400;
    if (sod < 0) {
        sod += 86400;
        days -= 1;
    }

    int32_t year;
    uint8_t month;
    uint8_t day;
    civil_from_days(days, &year, &month, &day);

    uint8_t hour = (uint8_t)(sod / 3600);
    uint8_t minute = (uint8_t)((sod % 3600) / 60);
    uint8_t second = (uint8_t)(sod % 60);

    (void)snprintf(out, out_len, "%04d-%02u-%02u %02u:%02u:%02u",
                   year, month, day, hour, minute, second);
    return 0;
}

int rtc_format_now_utc_datetime(char *out, size_t out_len)
{
    uint64_t now_s = get_utc_time();
    if (now_s == 0) {
        if (out && out_len) {
            out[0] = '\0';
        }
        return -ENODATA;
    }
    return rtc_format_utc_datetime((int64_t)now_s, out, out_len);
}
#endif

bool rtc_is_valid(void)
{
    k_mutex_lock(&rtc_lock, K_FOREVER);
    bool valid = utc_valid;
    k_mutex_unlock(&rtc_lock);
    return valid;
}

uint64_t rtc_get_utc_time_ms(void)
{
    k_mutex_lock(&rtc_lock, K_FOREVER);
    if (!utc_valid) {
        k_mutex_unlock(&rtc_lock);
        return 0;
    }
    int64_t now_uptime_ms = k_uptime_get();
    int64_t delta_ms = now_uptime_ms - base_uptime_ms;
    if (delta_ms < 0) {
        delta_ms = 0;
    }
    uint64_t now_ms = base_epoch_ms + (uint64_t)delta_ms;
    k_mutex_unlock(&rtc_lock);
    return now_ms;
}

int rtc_set_utc_time(uint64_t utc_epoch_s)
{
    if (utc_epoch_s == 0) {
        return -EINVAL;
    }

    int err = rtc_set_utc_time_ms(utc_epoch_s * 1000ULL);
    if (err) {
        return err;
    }

    /* Persist seconds for compatibility. */
    return app_settings_save_rtc_epoch(utc_epoch_s);
}

int rtc_set_utc_time_ms(uint64_t utc_epoch_ms)
{
    if (utc_epoch_ms == 0) {
        return -EINVAL;
    }

    k_mutex_lock(&rtc_lock, K_FOREVER);
    base_epoch_ms = utc_epoch_ms;
    base_uptime_ms = k_uptime_get();
    utc_valid = true;
    k_mutex_unlock(&rtc_lock);

    return 0;
}

uint32_t get_utc_time(void)
{
    uint64_t now_ms = rtc_get_utc_time_ms();
    if (now_ms == 0) {
        return 0;
    }

    uint64_t now_s = now_ms / 1000ULL;
    if (now_s > UINT32_MAX) {
        return UINT32_MAX;
    }

    return (uint32_t)now_s;
}

void init_rtc(void)
{
    static bool initialized;
    if (!initialized) {
        k_mutex_init(&rtc_lock);
        initialized = true;
    }

    uint64_t saved_epoch_s = app_settings_get_rtc_epoch();
    LOG_INF("RTC init: persisted rtc_epoch=%llu", saved_epoch_s);
    if (saved_epoch_s == 0) {
        k_mutex_lock(&rtc_lock, K_FOREVER);
        utc_valid = false;
        k_mutex_unlock(&rtc_lock);
        LOG_WRN("RTC not synchronized yet (no persisted epoch)");
        return;
    }

    k_mutex_lock(&rtc_lock, K_FOREVER);
    base_epoch_ms = saved_epoch_s * 1000ULL;
    base_uptime_ms = k_uptime_get();
    utc_valid = true;
    k_mutex_unlock(&rtc_lock);
    LOG_INF("RTC restored from persisted epoch");
}