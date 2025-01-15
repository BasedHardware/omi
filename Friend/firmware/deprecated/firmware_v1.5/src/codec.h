#pragma once
#include <zephyr/kernel.h>

// Callback
typedef void (*codec_callback)(uint8_t *data, size_t len);
void set_codec_callback(codec_callback callback);

// Integration
int codec_receive_pcm(int16_t *data, size_t len);
int codec_start();