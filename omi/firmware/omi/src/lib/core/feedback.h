#ifndef FEEDBACK_H
#define FEEDBACK_H

/**
 * @brief User feedback system for error/status indication
 *
 * Provides high-level feedback functions using LED (and potentially
 * haptic/sound in the future). Separates user feedback logic from
 * low-level driver control.
 */

/**
 * @brief Error indication functions
 *
 * Each error shows:
 * 1. RED alert blink (300ms)
 * 2. Pause (500ms)
 * 3. Color-coded pattern identifying the component
 *
 * Color codes:
 * - RED (1-2 blinks): System/LED
 * - YELLOW (1-2 blinks): Battery/Power
 * - GREEN (1 blink): Button/Input
 * - CYAN (1-2 blinks): Storage
 * - BLUE (1 blink): Communication
 * - MAGENTA (1-3 blinks): Audio
 */

void error_settings(void);
void error_led_driver(void);
void error_battery_init(void);
void error_battery_charge(void);
void error_button(void);
void error_haptic(void);
void error_sd_card(void);
void error_storage(void);
void error_transport(void);
void error_codec(void);
void error_microphone(void);

#endif
