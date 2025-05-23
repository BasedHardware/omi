#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <zephyr/drivers/sensor.h>
/**
 * @brief Initialize the BLE transport logic
 *
 * Initializes the BLE Logic
 *
 * @return 0 if successful, negative errno code if error
 */
int transport_start();
int transport_off();
int broadcast_audio_packets(uint8_t *buffer, size_t size);
struct bt_conn *get_current_connection();
#endif
