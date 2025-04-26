#pragma once

#include <stdint.h>

/**
 * @brief Initialize the Haptic Pin
 *
 * On Call, activates the haptic pin
 *
 * @return 0 if successful, negative errno code if error
 */
int init_haptic_pin();

/**
 * @brief Activate the haptic pin for a given duration
 *
 * On Call, starts the haptic pin, creating a vibration for the given duration in milliseconds
 *
 * @return a sound hopefully
 */
void play_haptic_milli(uint32_t duration);
