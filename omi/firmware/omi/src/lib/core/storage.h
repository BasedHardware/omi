#ifndef STORAGE_H
#define STORAGE_H

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE

#include <stdbool.h>

/**
 * @brief Initializes the Storage Transport thread
 *
 * Initializes the Storage Transport thread
 *
 * @return 0 if successful, negative errno code if error
 */
int storage_init();

/**
 * @brief Stops the current storage transfer
 *
 * Stops the current storage transfer
 */
void storage_stop_transfer();

/**
 * @brief Start auto-sync of stored audio data
 *
 * Called when BLE connects to automatically begin syncing
 * stored audio from the last saved offset.
 */
void storage_auto_sync_start(void);

/**
 * @brief Stop auto-sync of stored audio data
 *
 * Called when BLE disconnects to stop syncing and save current offset.
 */
void storage_auto_sync_stop(void);

/**
 * @brief Returns true when storage sync transfer is active.
 */
bool storage_transfer_active(void);

#endif // CONFIG_OMI_ENABLE_OFFLINE_STORAGE

#endif // STORAGE_H
