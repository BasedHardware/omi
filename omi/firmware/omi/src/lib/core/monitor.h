#ifndef MONITOR_H
#define MONITOR_H

#include <stdbool.h>
#include <stdint.h>

/**
 * @brief Initialize the monitoring system
 *
 * @return 0 on success, negative error code on failure
 */
int monitor_init(void);

/**
 * @brief Increment the GATT notify counter
 */
void monitor_inc_gatt_notify(void);

/**
 * @brief Increment the mic buffer counter
 */
void monitor_inc_mic_buffer(void);

/**
 * @brief Increment the broadcast audio counter
 */
void monitor_inc_broadcast_audio(void);

/**
 * @brief Increment the broadcast audio failed counter
 */
void monitor_inc_broadcast_audio_failed(void);

/**
 * @brief Increment the TX queue write counter
 */
void monitor_inc_tx_queue_write(void);

/**
 * @brief Increment the storage write counter
 */
void monitor_inc_storage_write(void);

/**
 * @brief Log all current metrics
 */
void monitor_log_metrics(void);

/**
 * @brief Reset all metrics counters
 */
void monitor_reset(void);

#endif // MONITOR_H
