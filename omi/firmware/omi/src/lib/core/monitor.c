#include "monitor.h"

#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(monitor, CONFIG_LOG_DEFAULT_LEVEL);

// Metric counters
static uint32_t gatt_notify_count = 0;
static uint32_t total_mic_buffer_bytes = 0;
static uint32_t broadcast_audio_count = 0;
static uint32_t broadcast_audio_failed_count = 0;
static uint32_t write_to_tx_queue_count = 0;
static uint32_t storage_write_count = 0;

int monitor_init(void)
{
    LOG_INF("Monitor system initialized");
    monitor_reset();
    return 0;
}

void monitor_inc_gatt_notify(void)
{
    gatt_notify_count++;
}

void monitor_inc_mic_buffer(void)
{
    total_mic_buffer_bytes++;
}

void monitor_inc_broadcast_audio(void)
{
    broadcast_audio_count++;
}

void monitor_inc_broadcast_audio_failed(void)
{
    broadcast_audio_failed_count++;
}

void monitor_inc_tx_queue_write(void)
{
    write_to_tx_queue_count++;
}

void monitor_inc_storage_write(void)
{
    storage_write_count++;
}

void monitor_log_metrics(void)
{
    LOG_INF("Metrics: Mic buffers: %u, GATT notify: %u, Broadcast: %u, Broadcast failed: %u, TX queue: %u, Storage: %u",
            total_mic_buffer_bytes,
            gatt_notify_count,
            broadcast_audio_count,
            broadcast_audio_failed_count,
            write_to_tx_queue_count,
            storage_write_count);
}

void monitor_reset(void)
{
    gatt_notify_count = 0;
    total_mic_buffer_bytes = 0;
    broadcast_audio_count = 0;
    broadcast_audio_failed_count = 0;
    write_to_tx_queue_count = 0;
    storage_write_count = 0;
    LOG_DBG("All metrics reset");
}
