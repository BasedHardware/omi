#pragma once
#include <zephyr/kernel.h>
int speaker_init();
uint16_t speak();
int play_boot_sound();
int init_haptic_pin();