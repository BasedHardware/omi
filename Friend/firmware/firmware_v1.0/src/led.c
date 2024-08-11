#include <zephyr/logging/log.h>
#include "led.h"
#include <zephyr/drivers/gpio.h>
#include "utils.h"

LOG_MODULE_REGISTER(led, CONFIG_LOG_DEFAULT_LEVEL);

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

void set_led_state(bool is_connected, bool is_recording)
{
    // Connected and recording - Solid Blue
    if (is_connected && is_recording) {
        set_led_red(false);
        set_led_green(false);
        set_led_blue(true);
    }
    // Connected but not recording - Blinking Blue
    else if (is_connected && !is_recording) {
        static bool blink_state = false;
        blink_state = !blink_state;
        set_led_red(false);
        set_led_green(false);
        set_led_blue(blink_state);
    }
    // Not connected - Solid Red
    else if (!is_connected) {
        set_led_red(true);
        set_led_green(false);
        set_led_blue(false);
    }
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
