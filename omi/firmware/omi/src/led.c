#include "lib/core/led.h"

#include <zephyr/drivers/pwm.h>
#include <zephyr/logging/log.h>

#include "lib/core/settings.h"
#include "lib/core/utils.h"

LOG_MODULE_REGISTER(led, CONFIG_LOG_DEFAULT_LEVEL);

// Define LED PWM specs from device tree
static const struct pwm_dt_spec led_red = PWM_DT_SPEC_GET(DT_NODELABEL(led_red));
static const struct pwm_dt_spec led_green = PWM_DT_SPEC_GET(DT_NODELABEL(led_green));
static const struct pwm_dt_spec led_blue = PWM_DT_SPEC_GET(DT_NODELABEL(led_blue));

int led_start()
{
    ASSERT_TRUE(pwm_is_ready_dt(&led_red));
    ASSERT_TRUE(pwm_is_ready_dt(&led_green));
    ASSERT_TRUE(pwm_is_ready_dt(&led_blue));
    LOG_INF("LEDs (PWM) started");
    return 0;
}

static void set_led_on_off(const struct pwm_dt_spec *led, bool on)
{
    if (!pwm_is_ready_dt(led)) {
        LOG_ERR("LED PWM device not ready");
        return;
    }

    uint32_t pulse_width_ns = 0;
    if (on) {
        uint8_t ratio = app_settings_get_dim_ratio();
        if (ratio > 100) {
            ratio = 100;
        }
        pulse_width_ns = (led->period * ratio) / 100;
    }

    pwm_set_pulse_dt(led, pulse_width_ns);
}

void set_led_red(bool on)
{
    set_led_on_off(&led_red, on);
}

void set_led_green(bool on)
{
    set_led_on_off(&led_green, on);
}

void set_led_blue(bool on)
{
    set_led_on_off(&led_blue, on);
}

void set_led_pwm(led_color_t color, uint8_t level)
{
    const struct pwm_dt_spec *led;

    switch (color) {
    case LED_RED:
        led = &led_red;
        break;
    case LED_GREEN:
        led = &led_green;
        break;
    case LED_BLUE:
        led = &led_blue;
        break;
    default:
        LOG_ERR("Invalid LED color");
        return;
    }

    if (!pwm_is_ready_dt(led)) {
        LOG_ERR("LED PWM device not ready");
        return;
    }

    if (level > 100) {
        level = 100;
    }

    uint32_t pulse_width_ns = (led->period * level) / 100;
    pwm_set_pulse_dt(led, pulse_width_ns);
}

void led_off(void)
{
    set_led_red(false);
    k_msleep(10);
    set_led_green(false);
    k_msleep(10);
    set_led_blue(false);
}
