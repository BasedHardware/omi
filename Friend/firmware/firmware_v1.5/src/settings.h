#pragma once
#include <zephyr/kernel.h>

int settings_start();

bool settings_read_enable();
void settings_write_enable(bool enable);