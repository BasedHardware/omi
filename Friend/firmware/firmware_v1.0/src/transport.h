#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <zephyr/types.h>

// Voice interaction functions
void start_voice_interaction(void);
void stop_voice_interaction(void);
extern bool voice_interaction_active;

// Other functions
int transport_start(void);
struct bt_conn *get_current_connection(void);
int broadcast_audio_packets(uint8_t *buffer, size_t size);
int bt_on(void);

#endif
