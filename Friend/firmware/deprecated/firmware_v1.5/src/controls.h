#pragma once

#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>

static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET_OR(DT_ALIAS(sw0), gpios, {0});
typedef void (*button_handler)();

int start_controls(void);
void set_button_handler(button_handler _handler);
