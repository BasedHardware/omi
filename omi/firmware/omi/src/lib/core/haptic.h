#ifndef HAPTIC_H_
#define HAPTIC_H_

#include <stdint.h>
#include <zephyr/bluetooth/conn.h>

/**
 * @brief Initialize the haptic driver.
 *
 * Configures the GPIO pin for the haptic motor.
 *
 * @return 0 on success, negative error code otherwise.
 */
int haptic_init(void);

/**
 * @brief Play a haptic effect for a specified duration.
 *
 * Activates the haptic motor for the given duration in milliseconds.
 * The duration is capped by MAX_HAPTIC_DURATION.
 *
 * @param duration Duration in milliseconds.
 */
void play_haptic_milli(uint32_t duration);

/**
 * @brief Register the Haptic BLE service.
 *
 * Registers the GATT service for controlling the haptic motor over Bluetooth.
 */
void register_haptic_service(void);

void haptic_off();

#endif // HAPTIC_H_
