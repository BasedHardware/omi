#pragma once
#include <zephyr/kernel.h>

int transport_start();

int broadcast_audio_packets(uint8_t *buffer, size_t size);

int save_audio_in_storage(buffer, size);