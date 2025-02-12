#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <zephyr/drivers/sensor.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// State variables
extern bool voice_interaction_active;

typedef struct sensors {
    struct sensor_value a_x;
    struct sensor_value a_y;
    struct sensor_value a_z;
    struct sensor_value g_x;
    struct sensor_value g_y;
    struct sensor_value g_z;
} sensors;

// Function declarations
void start_voice_interaction(void);
void stop_voice_interaction(void);
void handle_voice_data(uint8_t *data, size_t len);

/**
 * @brief Initialize the BLE transport logic
 *
 * Initializes the BLE Logic
 *
 * @return 0 if successful, negative errno code if error
 */
int transport_start();
int broadcast_audio_packets(uint8_t *buffer, size_t size);
struct bt_conn *get_current_connection();
int bt_on();
int bt_off();

void accel_off();

void speak_stream(uint8_t* data, uint16_t length);

#endif
