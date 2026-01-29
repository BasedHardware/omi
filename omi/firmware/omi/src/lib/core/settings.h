#ifndef SETTINGS_H
#define SETTINGS_H

#include <stdint.h>
#include <zephyr/drivers/rtc.h>

/**
 * @brief Initialize the settings subsystem.
 *
 * This loads any persisted settings from flash into memory.
 *
 * @return 0 on success, negative error code otherwise.
 */
int app_settings_init(void);

/**
 * @brief Save the dim light ratio setting.
 *
 * @param new_ratio The new ratio value (e.g., 0-100).
 * @return 0 on success, negative error code otherwise.
 */
int app_settings_save_dim_ratio(uint8_t new_ratio);

/**
 * @brief Get the current dim light ratio.
 *
 * @return The current ratio value.
 */
uint8_t app_settings_get_dim_ratio(void);

/**
 * @brief Save the microphone gain setting.
 *
 * @param new_gain The new gain level (0-8).
 * @return 0 on success, negative error code otherwise.
 */
int app_settings_save_mic_gain(uint8_t new_gain);

/**
 * @brief Get the current microphone gain.
 *
 * @return The current gain level (0-8).
 */
uint8_t app_settings_get_mic_gain(void);

/**
 * @brief Save the RTC timestamp setting.
 *
 * @param ts The new RTC timestamp.
 * @return 0 on success, negative error code otherwise.
 */
int app_settings_save_rtc_timestamp(struct rtc_time ts);

/**
 * @brief Get the current RTC timestamp.
 *
 * @return The current RTC timestamp.
 */
struct rtc_time app_settings_get_rtc_timestamp(void);

/**
 * @brief Save the UTC epoch time base (seconds).
 *
 * This is used by the application timekeeping layer to provide a stable
 * increasing UTC time while the device is running.
 *
 * @param epoch_s UTC time in seconds since 1970-01-01.
 * @return 0 on success, negative error code otherwise.
 */
int app_settings_save_rtc_epoch(uint64_t epoch_s);

/**
 * @brief Get the persisted UTC epoch time base (seconds).
 *
 * @return UTC seconds since 1970-01-01, or 0 if not set.
 */
uint64_t app_settings_get_rtc_epoch(void);

/**
 * @brief Save an LSM6DSL timestamp base for timekeeping across system_off.
 *
 * When epoch_s is non-zero, the base becomes valid; when epoch_s is zero, the
 * stored base is cleared.
 */
int app_settings_save_lsm6dsl_time_base(uint64_t epoch_s, uint32_t imu_timestamp);

/**
 * @brief Get the saved LSM6DSL timestamp base.
 *
 * @param epoch_s Output epoch seconds (0 if not set).
 * @param imu_timestamp Output IMU timestamp counter.
 */
int app_settings_get_lsm6dsl_time_base(uint64_t *epoch_s, uint32_t *imu_timestamp);

#endif // SETTINGS_H
