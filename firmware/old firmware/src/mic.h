#pragma once

typedef void (*mix_handler)(int16_t *);
int mic_start();
void set_mic_callback(mix_handler _callback);
