#pragma once

#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>

// Define GPIO specs for LEDs
static const struct gpio_dt_spec led_red = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);
static const struct gpio_dt_spec led_green = GPIO_DT_SPEC_GET(DT_ALIAS(led1), gpios);
static const struct gpio_dt_spec led_blue = GPIO_DT_SPEC_GET(DT_ALIAS(led2), gpios);
static const struct gpio_dt_spec led_white = GPIO_DT_SPEC_GET(DT_ALIAS(led3), gpios);  // Add this line for the white LED

// Function prototypes
int led_start();
void set_led_red(bool on);
void set_led_green(bool on);
void set_led_blue(bool on);
void set_led_white(bool on);  // Add this function prototype for the white LED
