#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

struct bt_conn;
/**
 * @brief Initialize the BLE transport logic
 *
 * Initializes the BLE Logic
 *
 * @return 0 if successful, negative errno code if error
 */
int transport_start(bool offline_storage_available);
int broadcast_audio_packets(uint8_t *buffer, size_t size);
struct bt_conn *get_current_connection();
int bt_on();
int bt_off();

void accel_off();
#endif
