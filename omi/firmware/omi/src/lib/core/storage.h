#ifndef STORAGE_H
#define STORAGE_H

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE

#include <stdbool.h>
#include <stdint.h>

/**
 * @brief Initializes the Storage Transport thread
 *
 * @return 0 if successful, negative errno code if error
 */
int storage_init();

/**
 * @brief Stops the current storage transfer
 */
void storage_stop_transfer();

/**
 * @brief Returns true when storage sync transfer is active.
 */
bool storage_transfer_active(void);

void storage_connection_changed(void);

uint32_t storage_live_session(void);

void storage_queue_live_mark(uint64_t ring_id, uint64_t ring_seq, uint16_t live_index, uint32_t session);

#endif // CONFIG_OMI_ENABLE_OFFLINE_STORAGE

#endif // STORAGE_H
