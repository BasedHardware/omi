#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <zephyr/types.h> // For uint8_t, size_t
#include <zephyr/drivers/sensor.h>
typedef struct sensors {

	struct sensor_value a_x;
	struct sensor_value a_y;
	struct sensor_value a_z;
    struct sensor_value g_x;
    struct sensor_value g_y;
    struct sensor_value g_z;

};
/**
 * @brief Initialize the BLE transport logic
 *
 * Initializes the BLE Logic
 *
 * @return 0 if successful, negative errno code if error
 */
int transport_start();
struct bt_conn *get_current_connection();
int broadcast_audio_packets(uint8_t *buffer, size_t size);

// Voice interaction function prototypes and variable
void start_voice_interaction(void);
void stop_voice_interaction(void);
extern bool voice_interaction_active;

int bt_on();
#endif
