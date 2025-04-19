/**
 * @file transport.h
 * @brief Bluetooth communication interface for audio streaming
 * 
 * This module handles Bluetooth Low Energy (BLE) communication, including
 * service advertisement, connection management, and audio data transmission.
 * It provides functions to initialize BLE transport, broadcast audio packets,
 * and control the Bluetooth radio state.
 */
#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <zephyr/drivers/sensor.h>

/**
 * @brief Sensor data structure for accelerometer and gyroscope readings
 * 
 * Contains 3-axis accelerometer and 3-axis gyroscope sensor values
 * that can be transmitted over Bluetooth to connected devices.
 */
typedef struct sensors {
	struct sensor_value a_x;  /* X-axis acceleration */
	struct sensor_value a_y;  /* Y-axis acceleration */
	struct sensor_value a_z;  /* Z-axis acceleration */
    struct sensor_value g_x;  /* X-axis angular velocity */
    struct sensor_value g_y;  /* Y-axis angular velocity */
    struct sensor_value g_z;  /* Z-axis angular velocity */
};

/**
 * @brief Initialize the BLE transport logic
 *
 * Sets up and starts Bluetooth services, including device information,
 * audio transmission service, and sensor data services. Begins advertising
 * to allow connections from other devices.
 *
 * @return 0 if successful, negative errno code if error
 */
int transport_start();

/**
 * @brief Broadcast encoded audio packets via Bluetooth
 * 
 * Sends encoded audio data to connected Bluetooth devices through
 * the appropriate audio characteristic.
 *
 * @param buffer Pointer to encoded audio data
 * @param size Size of the audio data in bytes
 * @return 0 if successful, negative errno code if error
 */
int broadcast_audio_packets(uint8_t *buffer, size_t size);

/**
 * @brief Send test message directly over Bluetooth
 * 
 * Sends a test message via the test data characteristic. This function
 * bypasses the audio data pipeline for simpler debugging.
 * 
 * @param message Pointer to the message string
 * @param length Length of the message
 * @return 0 on success, negative error code on failure
 */
int send_test_message(const char *message, size_t length);

/**
 * @brief Get the current active Bluetooth connection
 * 
 * Returns a pointer to the currently established Bluetooth connection,
 * or NULL if no device is connected.
 *
 * @return Pointer to the active bt_conn structure, or NULL if not connected
 */
struct bt_conn *get_current_connection();

/**
 * @brief Turn on the Bluetooth radio
 * 
 * Enables the Bluetooth hardware and starts advertising.
 *
 * @return 0 if successful, negative errno code if error
 */
int bt_on();

/**
 * @brief Turn off the Bluetooth radio
 * 
 * Stops advertising and disables the Bluetooth hardware to save power.
 *
 * @return 0 if successful, negative errno code if error
 */
int bt_off();

/**
 * @brief Turn off the IMU sensor
 * 
 * Disables the IMU to save power when motion sensing is not needed.
 */
void imu_off();
#endif