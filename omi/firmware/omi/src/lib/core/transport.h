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
 * Force subsequent audio delivery to SD before draining upstream producers.
 */
int transport_begin_shutdown(void);

/**
 * Restore normal live/storage routing after a cancelled shutdown.
 */
void transport_cancel_shutdown(void);

/**
 * @brief Durably drain accepted audio before system shutdown
 *
 * The microphone must be stopped before calling this function. It forces all
 * queued frames to offline storage, flushes the packer tail, and waits for the
 * SD worker to sync the media.
 *
 * @return 0 if every accepted frame is durable, negative errno code otherwise
 */
int transport_prepare_shutdown(void);

/**
 * @brief Broadcast audio packets over BLE
 *
 * @param buffer Buffer containing audio data
 * @param size Size of the audio data
 * @return 0 if successful, negative errno code if error
 */
int broadcast_audio_packets(uint8_t *buffer, size_t size);

/**
 * @brief Acquire a referenced snapshot of the current BLE connection
 *
 * The caller must release a non-NULL result with bt_conn_unref().
 *
 * @return Referenced connection, or NULL if not connected
 */
struct bt_conn *get_current_connection(void);

/**
 * @brief True after the connect-time audio queue and packer tail have been
 * committed to the SD ring.
 *
 * Ring INFO/READ must wait for this barrier so their first snapshot cannot
 * omit audio that was already queued before the connection.
 */
bool transport_storage_snapshot_ready(void);

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
