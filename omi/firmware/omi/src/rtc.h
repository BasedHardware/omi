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

#define RTC_MIN_VALID_EPOCH 1700000000U
#define RTC_TIMESTAMP_UPTIME_FLAG 0x80000000U

/**
 * @brief Initialize application timekeeping.
 *
 * Restores a diagnostic clock from persisted settings if available. Restoration
 * never establishes trusted recording time.
 */
void init_rtc(void);

/**
 * @brief Get current UTC epoch seconds.
 *
 * May be a stale restored epoch; use rtc_get_record_timestamp() for recordings.
 * @return Diagnostic epoch seconds, or 0 if no time base is available.
 */
uint32_t get_utc_time(void);

/**
 * @brief Check whether an epoch time base is available (restored or synced).
 * This is not a trust signal. Do not use it to choose recording timestamps.
 */
bool rtc_is_valid(void);

/** @brief True only after a phone time sync in this boot, never after restore. */
bool rtc_is_trusted(void);

/**
 * @brief Recording timestamp: trusted epoch or bit-31 flagged seconds since boot.
 * Always returns a timestamp, including before any sync. The low 31 bits of a
 * flagged timestamp are uptime, never UTC. Trust and epoch are sampled together.
 */
uint32_t rtc_get_record_timestamp(void);

/**
 * @brief Set UTC epoch seconds from a phone sync and establish trust.
 *
 * Persists a base value to settings and uses monotonic uptime to produce a
 * stable increasing time while running.
 */
int rtc_set_utc_time(uint64_t utc_epoch_s);

/**
 * @brief Restore a diagnostic epoch in milliseconds without establishing trust.
 * Used by the IMU boot adjustment; power loss/wrap makes it unsuitable as proof
 * of wall-clock recording time.
 *
 * @param utc_epoch_ms UTC epoch milliseconds since 1970-01-01.
 */
int rtc_restore_utc_time_ms(uint64_t utc_epoch_ms);

/**
 * @brief Get diagnostic epoch milliseconds (may be restored and stale).
 *
 * @return Diagnostic epoch milliseconds, or 0 if no time base is available.
 */
uint64_t rtc_get_utc_time_ms(void);

/**
 * @brief Format diagnostic time; a restored value is not trusted recording time.
 *
 * @return 0 on success, -ENODATA if unsynchronized, otherwise negative errno.
 */
int rtc_format_now_utc_datetime(char *out, size_t out_len);

#endif
