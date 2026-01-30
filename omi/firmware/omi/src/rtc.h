#ifndef OMI_RTC_H_
#define OMI_RTC_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/**
 * @brief Minimum buffer size for formatted UTC datetime strings.
 *
 * Format: "YYYY-MM-DD HH:MM:SS" + NUL terminator.
 */
#define RTC_UTC_DATETIME_STRLEN 20

/**
 * @brief Initialize application timekeeping.
 *
 * Restores RTC from persisted settings if available.
 */
void init_rtc(void);

/**
 * @brief Get current UTC epoch seconds.
 *
 * @return UTC epoch seconds, or 0 if the clock is not yet synchronized.
 */
uint32_t get_utc_time(void);

/**
 * @brief Check whether UTC time is valid/synchronized.
 */
bool rtc_is_valid(void);

/**
 * @brief Set/synchronize UTC epoch seconds.
 *
 * Persists a base value to settings and uses monotonic uptime to produce a
 * stable increasing time while running.
 */
int rtc_set_utc_time(uint64_t utc_epoch_s);

/**
 * @brief Set/synchronize UTC epoch in milliseconds.
 *
 * @param utc_epoch_ms UTC epoch milliseconds since 1970-01-01.
 */
int rtc_set_utc_time_ms(uint64_t utc_epoch_ms);

/**
 * @brief Get UTC epoch milliseconds.
 *
 * @return UTC epoch milliseconds, or 0 if unsynchronized.
 */
uint64_t rtc_get_utc_time_ms(void);

/**
 * @brief Convenience helper to format the current UTC time.
 *
 * @return 0 on success, -ENODATA if unsynchronized, otherwise negative errno.
 */
int rtc_format_now_utc_datetime(char *out, size_t out_len);

#endif