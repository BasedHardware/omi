#pragma once
#include <zephyr/kernel.h>

int read_audio_in_storage(void);

int transport_start();

int broadcast_audio_packets(uint8_t *buffer, size_t size);