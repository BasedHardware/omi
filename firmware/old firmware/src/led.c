#include "led.h"
#include <zephyr/drivers/gpio.h>
#include "utils.h"

int led_start()
{
    ASSERT_TRUE(gpio_is_ready_dt(&led_red));
    ASSERT_OK(gpio_pin_configure_dt(&led_red, GPIO_OUTPUT_INACTIVE));
    ASSERT_TRUE(gpio_is_ready_dt(&led_green));
    ASSERT_OK(gpio_pin_configure_dt(&led_green, GPIO_OUTPUT_INACTIVE));
    ASSERT_TRUE(gpio_is_ready_dt(&led_blue));
    ASSERT_OK(gpio_pin_configure_dt(&led_blue, GPIO_OUTPUT_INACTIVE));
    printk("LEDs started\n");
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