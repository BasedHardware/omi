/**
 * @file led.h
 * @brief LED control interface
 * 
 * This module provides functionality to control the RGB LEDs on the device.
 * It includes functions for initializing the LED GPIOs and setting individual
 * red, green, and blue LEDs on or off. These LEDs are used to indicate device
 * status such as power, connection state, and operational modes.
 */
#ifndef LED_H
#define LED_H

#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>

/**
 * @brief GPIO specification for the red LED
 * 
 * Device tree specification for the red LED GPIO, used for
 * power and error status indications.
 */
static const struct gpio_dt_spec led_red = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(led_red), gpios, {0});

/**
 * @brief GPIO specification for the green LED
 * 
 * Device tree specification for the green LED GPIO, used for
 * charging and operational status indications.
 */
static const struct gpio_dt_spec led_green = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(led_green), gpios, {0});

/**
 * @brief GPIO specification for the blue LED
 * 
 * Device tree specification for the blue LED GPIO, used for
 * Bluetooth connection status indications.
 */
static const struct gpio_dt_spec led_blue = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(led_blue), gpios, {0});

/**
 * @brief Initialize the LEDs
 *
 * Initializes the LEDs
 *
 * @return 0 if successful, negative errno code if error
 */
int led_start();

/**
 * @brief Control the red LED
 * 
 * Turns the red LED on or off. Typically used to indicate power status
 * or error conditions.
 *
 * @param on true to turn LED on, false to turn it off
 */
void set_led_red(bool on);

/**
 * @brief Control the green LED
 * 
 * Turns the green LED on or off. Typically used to indicate charging
 * status or successful operations.
 *
 * @param on true to turn LED on, false to turn it off
 */
void set_led_green(bool on);

/**
 * @brief Control the blue LED
 * 
 * Turns the blue LED on or off. Typically used to indicate Bluetooth
 * connection status.
 *
 * @param on true to turn LED on, false to turn it off
 */
void set_led_blue(bool on);

#endif