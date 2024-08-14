// src/button.h
#ifndef BUTTON_H
#define BUTTON_H

#include <zephyr/drivers/gpio.h>

#define BUTTON_PIN_1 4
#define BUTTON_PIN_2 5

extern const struct gpio_dt_spec button;

void button_init(void);
bool is_button_pressed(void);

#endif // BUTTON_H