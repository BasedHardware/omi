#pragma once
#include <zephyr/kernel.h>

extern uint32_t storage_action;
extern int notification_value;

int read_audio_in_storage(void);

int transport_start();

int broadcast_audio_packets(uint8_t *buffer, size_t size);