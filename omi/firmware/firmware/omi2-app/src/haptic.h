/**
 * @file haptic.h
 * @brief Header file for haptic feedback functionality
 *
 * This file contains function declarations for controlling haptic feedback
 * on the device, such as vibration motors or actuators.
 */

#ifndef HAPTIC_H
#define HAPTIC_H

#include <zephyr/kernel.h>

/**
 * @brief Initialize the haptic feedback pin
 *
 * Configures the GPIO pin used to control the haptic actuator
 *
 * @return 0 on success, negative error code on failure
 */
int init_haptic_pin(void);

/**
 * @brief Trigger haptic feedback for specified duration
 *
 * Activates the haptic actuator for the specified duration in milliseconds
 *
 * @param duration_ms Duration in milliseconds to activate the haptic feedback
 */
void play_haptic_milli(uint32_t duration_ms);

#endif /* HAPTIC_H */ 