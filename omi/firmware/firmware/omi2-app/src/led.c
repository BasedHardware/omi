/**
 * @file led.c
 * @brief Implementation of LED control functionality
 * 
 * This file contains the implementation of functions to control the 
 * device's RGB LEDs. It provides functionality to initialize the LEDs
 * and set their individual states (on/off) for indicating device status.
 */
#include <zephyr/logging/log.h>
#include <zephyr/drivers/gpio.h>
#include "led.h"
#include "utils.h"

LOG_MODULE_REGISTER(led, CONFIG_LOG_DEFAULT_LEVEL);

/**
 * @brief Initialize the LED GPIO pins
 * 
 * Sets up each LED GPIO pin (red, green, blue) as output pins
 * with initial state set to inactive (off). Verifies that each
 * LED controller is ready before configuring.
 * 
 * @return 0 on success, negative error code on failure
 */
int led_start()
{
    ASSERT_TRUE(gpio_is_ready_dt(&led_red));
    ASSERT_OK(gpio_pin_configure_dt(&led_red, GPIO_OUTPUT_INACTIVE));
    ASSERT_TRUE(gpio_is_ready_dt(&led_green));
    ASSERT_OK(gpio_pin_configure_dt(&led_green, GPIO_OUTPUT_INACTIVE));
    ASSERT_TRUE(gpio_is_ready_dt(&led_blue));
    ASSERT_OK(gpio_pin_configure_dt(&led_blue, GPIO_OUTPUT_INACTIVE));
    LOG_INF("LEDs started");
    return 0;
}

/**
 * @brief Control the red LED state
 * 
 * Sets the red LED to either on or off state based on the input parameter.
 * 
 * @param on true to turn the LED on, false to turn it off
 */
void set_led_red(bool on)
{
    gpio_pin_set_dt(&led_red, on);
}

/**
 * @brief Control the green LED state
 * 
 * Sets the green LED to either on or off state based on the input parameter.
 * 
 * @param on true to turn the LED on, false to turn it off
 */
void set_led_green(bool on)
{
    gpio_pin_set_dt(&led_green, on);
}

/**
 * @brief Control the blue LED state
 * 
 * Sets the blue LED to either on or off state based on the input parameter.
 * 
 * @param on true to turn the LED on, false to turn it off
 */
void set_led_blue(bool on)
{
    gpio_pin_set_dt(&led_blue, on);
}
