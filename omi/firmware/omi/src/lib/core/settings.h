#ifndef SETTINGS_H
#define SETTINGS_H

#include <stddef.h>
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
 * @brief Save the device name setting.
 *
 * @param new_name The new device name (max 10 characters).
 * @return 0 on success, negative error code otherwise.
 */
int app_settings_save_device_name(const char *new_name);

/**
 * @brief Get the current device name.
 *
 * @param name_buffer Buffer to store the device name.
 * @param buffer_size Size of the buffer.
 * @return 0 on success, negative error code otherwise.
 */
int app_settings_get_device_name(char *name_buffer, size_t buffer_size);

#endif // SETTINGS_H
