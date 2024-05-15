#pragma once
#include <zephyr/kernel.h>

int transport_start();
int broadcast_audio_packets(uint8_t *buffer, size_t size);
typedef void (*transport_subscribed_handler)();
typedef void (*transport_unsubscribed_handler)();
struct transport_cb
{
    void (*subscribed)();
    void (*unsubscribed)();
};
void set_transport_callbacks(struct transport_cb *_callbacks);
void set_allowed(bool allowed);
void set_bt_batterylevel(uint8_t level);