#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#ifdef CONFIG_OMI_ENABLE_BATTERY
extern uint8_t battery_percentage;
#endif
/**
 * @brief Initialize the BLE transport logic
 *
 * Initializes the BLE Logic
 *
 * @return 0 if successful, negative errno code if error
 */
int transport_start();

/**
 * @brief Turn off the BLE transport
 *
 * @return 0 if successful, negative errno code if error
 */
int transport_off();

/**
 * @brief Clear all stored BLE bonds and resume connectable advertising.
 *
 * Disconnects the active central (if any), removes every paired device via
 * bt_unpair(BT_ID_DEFAULT, NULL), and restarts advertising so a new phone
 * can pair. Required before shipping CONFIG_OMI_REQUIRE_BLE_ENCRYPTION with
 * CONFIG_BT_MAX_PAIRED=1.
 *
 * @return 0 on success, negative errno on failure
 */
int transport_clear_bonds(void);

/**
 * @brief Broadcast audio packets over BLE
 *
 * @param buffer Buffer containing audio data
 * @param size Size of the audio data
 * @return 0 if successful, negative errno code if error
 */
int broadcast_audio_packets(uint8_t *buffer, size_t size);

/**
 * @brief Get the current BLE connection
 *
 * @return Pointer to current connection, or NULL if not connected
 */
struct bt_conn *get_current_connection();

/**
 * @brief Acquire / release a shared BLE TX-throttle slot.
 *
 * The audio pusher and the storage-sync path both take a slot before each bulk
 * notification, capping their COMBINED in-flight count at
 * (CONFIG_BT_CONN_TX_MAX - reserved) so a couple of TX buffers always stay free
 * for short control notifications (battery / charging / status). The slot is
 * released from the notification's bt_gatt_notify_cb completion callback.
 *
 * @return acquire: 0 on success, negative errno on timeout.
 */
int transport_bulk_tx_acquire(k_timeout_t timeout);
void transport_bulk_tx_release(void);

#endif // TRANSPORT_H
