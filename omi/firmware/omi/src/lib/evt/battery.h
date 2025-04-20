#ifndef BATTERY_H
#define BATTERY_H

#include <zephyr/kernel.h>
#include <zephyr/input/input.h>

extern bool is_charging;

int bat_init(void);

#endif // BATTERY_H