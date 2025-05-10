#include <zephyr/logging/log.h>
#include <zephyr/drivers/gpio.h>
#include "lib/dk2/led.h"
#include "lib/dk2/utils.h"

LOG_MODULE_REGISTER(led, CONFIG_LOG_DEFAULT_LEVEL);

// Define LED pins using the same pattern as in evt/led.c
const struct gpio_dt_spec led_red = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(led_red), gpios, {0});
const struct gpio_dt_spec led_green = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(led_green), gpios, {0});
const struct gpio_dt_spec led_blue = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(led_blue), gpios, {0});

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

void set_led_red(bool on)
{
    gpio_pin_set_dt(&led_red, on);
}

void set_led_green(bool on)
{
    gpio_pin_set_dt(&led_green, on);
}

void set_led_blue(bool on)
{
    gpio_pin_set_dt(&led_blue, on);
}
