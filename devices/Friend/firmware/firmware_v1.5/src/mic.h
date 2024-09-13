#pragma once

int mic_start();
int mic_resume();
int mic_pause();

typedef void (*mix_handler)(int16_t *);
void set_mic_callback(mix_handler _callback);
