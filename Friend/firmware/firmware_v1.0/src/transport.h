#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

// Voice interaction functions
extern bool voice_interaction_active;
void start_voice_interaction(void);
void stop_voice_interaction(void);

// Declare handle_voice_data as non-static
int handle_voice_data(uint8_t *data, size_t len);

// Existing declarations...
int transport_start(void);
struct bt_conn *get_current_connection(void);
int broadcast_audio_packets(uint8_t *buffer, size_t size);
int bt_on(void);

#endif
