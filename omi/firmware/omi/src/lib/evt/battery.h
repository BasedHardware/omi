#ifndef BATTERY_H
#define BATTERY_H

#include <zephyr/input/input.h>
#include <zephyr/kernel.h>

extern bool is_charging;

int bat_init(void);

#endif // BATTERY_H