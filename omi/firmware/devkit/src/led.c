#include <zephyr/logging/log.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/pwm.h>
#include "led.h"
#include "utils.h"

LOG_MODULE_REGISTER(led, CONFIG_LOG_DEFAULT_LEVEL);

// Define PWM devices for LEDs
static const struct pwm_dt_spec pwm_led_red = PWM_DT_SPEC_GET(DT_ALIAS(pwm_led0));
static const struct pwm_dt_spec pwm_led_green = PWM_DT_SPEC_GET(DT_ALIAS(pwm_led1));
static const struct pwm_dt_spec pwm_led_blue = PWM_DT_SPEC_GET(DT_ALIAS(pwm_led2));

int led_start()
{
    ASSERT_TRUE(gpio_is_ready_dt(&led_red));
    ASSERT_OK(gpio_pin_configure_dt(&led_red, GPIO_OUTPUT_INACTIVE));
    ASSERT_TRUE(gpio_is_ready_dt(&led_green));
    ASSERT_OK(gpio_pin_configure_dt(&led_green, GPIO_OUTPUT_INACTIVE));
    ASSERT_TRUE(gpio_is_ready_dt(&led_blue));
    ASSERT_OK(gpio_pin_configure_dt(&led_blue, GPIO_OUTPUT_INACTIVE));
    
    ASSERT_TRUE(pwm_is_ready_dt(&pwm_led_red));
    ASSERT_TRUE(pwm_is_ready_dt(&pwm_led_green));
    ASSERT_TRUE(pwm_is_ready_dt(&pwm_led_blue));
    
    LOG_INF("LEDs started with PWM support");
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

void set_led_brightness(const struct pwm_dt_spec *pwm_led, uint8_t brightness)
{
    if (brightness > 100) brightness = 100; // Cap brightness at 100%
    uint32_t pulse_width = (pwm_led->period * brightness) / 100;
    pwm_set_dt(pwm_led, pwm_led->period, pulse_width);
}

void set_led_red_brightness(uint8_t brightness)
{
    set_led_brightness(&pwm_led_red, brightness);
}

void set_led_green_brightness(uint8_t brightness)
{
    set_led_brightness(&pwm_led_green, brightness);
}

void set_led_blue_brightness(uint8_t brightness)
{
    set_led_brightness(&pwm_led_blue, brightness);
}

// API to set brightness for a specific LED
void set_led_brightness_api(const char *led_color, uint8_t brightness)
{
    if (strcmp(led_color, "red") == 0)
    {
        set_led_red_brightness(brightness);
    }
    else if (strcmp(led_color, "green") == 0)
    {
        set_led_green_brightness(brightness);
    }
    else if (strcmp(led_color, "blue") == 0)
    {
        set_led_blue_brightness(brightness);
    }
    else
    {
        LOG_ERR("Invalid LED color: %s", led_color);
    }
}
