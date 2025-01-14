#pragma once

#define CHARGE_NOT_CHARGING 0
#define CHARGE_CHARGING 1

bool is_battery_charging(void);
int get_battery_voltage(void);
int get_battery_percentage(void);
int battery_start(void);