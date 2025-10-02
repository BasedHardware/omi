#ifndef SETTINGS_H
#define SETTINGS_H

#include <stdint.h>

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
 * @brief Save the storage offset setting.
 *
 * @param offset_val The offset value to save.
 * @return 0 on success, negative error code otherwise.
 */
int app_settings_save_storage_offset(uint32_t offset_val);

/**
 * @brief Load the storage offset setting.
 *
 * @param offset_val Pointer to store the loaded offset value.
 * @return 0 on success, negative error code otherwise.
 */
int app_settings_load_storage_offset(uint32_t *offset_val);

/**
 * @brief Save the base timestamp for SD card file timing.
 *
 * @param timestamp_ms Base timestamp in milliseconds (Unix epoch).
 * @return 0 on success, negative error code otherwise.
 */
int app_settings_save_base_timestamp(uint64_t timestamp_ms);

/**
 * @brief Get the saved base timestamp.
 *
 * @param timestamp_ms Pointer to store the timestamp.
 * @return 0 on success, negative error code otherwise.
 */
int app_settings_get_base_timestamp(uint64_t *timestamp_ms);

#endif // SETTINGS_H
