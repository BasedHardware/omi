#include "deepsleep_button.h"
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/drivers/gpio.h>

LOG_MODULE_REGISTER(button, LOG_LEVEL_INF);

const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(DT_ALIAS(sw0), gpios);

void deepsleep_button_init(void)
{
    int ret;

    // Configure the button pin as an input with pull-up resistor
    ret = gpio_pin_configure_dt(&button, GPIO_INPUT | GPIO_PULL_UP);
    if (ret != 0) {
        LOG_ERR("Error %d: failed to configure button pin", ret);
        return;
    }

    LOG_INF("Button initialized");
}

bool is_button_pressed(void)
{
    return gpio_pin_get_dt(&button) == 0; // Assuming active low
}
