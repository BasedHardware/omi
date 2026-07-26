#ifndef SETTINGS_H
#define SETTINGS_H

#include <stdbool.h>
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
 * This records the most recent live synchronization for historical context.
 * Loading it after reboot never makes RTC time valid.
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
 * @brief Save or consume the legacy LSM6DSL elapsed-time marker.
 *
 * A zero epoch consumes the marker. CV1 production does not create a new
 * marker because its unbounded system-off interval cannot be recovered safely
 * from the wrapping 24-bit counter.
 */
int app_settings_save_lsm6dsl_time_base(uint64_t epoch_s, uint32_t imu_timestamp);

/**
 * @brief Get the saved LSM6DSL timestamp base.
 *
 * @param epoch_s Output epoch seconds (0 if not set).
 * @param imu_timestamp Output IMU timestamp counter.
 */
int app_settings_get_lsm6dsl_time_base(uint64_t *epoch_s, uint32_t *imu_timestamp);

typedef struct {
    uint64_t affected_start_seq;
    uint64_t replacement_start_seq;
    uint64_t attempted_write_seq;
    uint64_t metadata_generation;
    uint64_t baseline_read_seq;
    uint64_t baseline_write_seq;
    uint64_t baseline_dropped_packets;
    uint32_t capacity_packets;
    uint32_t batch_packets;
    uint32_t preimage_crc32;
    bool active;
} app_sd_ring_quarantine_t;

/**
 * Persist a one-time write-ahead quarantine for a legacy CRC-less SD batch.
 * This marker lives in MCU NVS, outside the failing SD data path.
 */
int app_settings_save_sd_ring_quarantine(uint64_t affected_start_seq,
                                         uint64_t replacement_start_seq,
                                         uint64_t attempted_write_seq,
                                         uint64_t metadata_generation,
                                         uint64_t baseline_read_seq,
                                         uint64_t baseline_write_seq,
                                         uint64_t baseline_dropped_packets,
                                         uint32_t capacity_packets,
                                         uint32_t batch_packets,
                                         uint32_t preimage_crc32);
int app_settings_clear_sd_ring_quarantine(void);
app_sd_ring_quarantine_t app_settings_get_sd_ring_quarantine(void);
int app_settings_get_sd_ring_quarantine_load_error(void);

#endif // SETTINGS_H
