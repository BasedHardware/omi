#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device_runtime.h>
#include "lib/dk2/mic.h"
#include "lib/dk2/codec.h"
#include "lib/dk2/config.h"
#include "lib/dk2/transport.h"
LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

bool is_connected = false;

// TODO: remove these metrics
uint32_t gatt_notify_count = 0;
uint32_t total_mic_buffer_bytes = 0;
uint32_t broadcast_audio_count = 0;
uint32_t write_to_tx_queue_count = 0;

static void codec_handler(uint8_t *data, size_t len)
{
    broadcast_audio_count++;
    int err = broadcast_audio_packets(data, len);
    if (err)
    {
        LOG_ERR("Failed to broadcast audio packets: %d", err);
    }
}

static void mic_handler(int16_t *buffer)
{
    // Track total bytes processed (each sample is 2 bytes)
    total_mic_buffer_bytes += 1;
    
    int err = codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES);
    if (err)
    {
        LOG_ERR("Failed to process PCM data: %d", err);
    }
}

int main(void)
{
	int ret;

	printk("Starting omi2 ...\n");
	
	// Indicate transport initialization
	LOG_PRINTK("\n");
	LOG_INF("Initializing transport...\n");

	// Start transport
	int transportErr;
	transportErr = transport_start();
	if (transportErr)
	{
		LOG_ERR("Failed to start transport (err %d)", transportErr);
		return transportErr;
	}
	
	// Initialize codec
	LOG_INF("Initializing codec...\n");
	
	// Set codec callback
	set_codec_callback(codec_handler);
	ret = codec_start();
	if (ret)
	{
		LOG_ERR("Failed to start codec: %d", ret);
		return ret;
	}
	
	// Initialize microphone
	LOG_INF("Initializing microphone...\n");
	set_mic_callback(mic_handler);
	ret = mic_start();
	if (ret)
	{
		LOG_ERR("Failed to start microphone: %d", ret);
		return ret;
	}
	
	LOG_INF("Device initialized successfully\n");

	while (1) {
        LOG_INF("Running omi2...\n");
        
        // Update connection status and buffer stats in logs
        if (is_connected) {
            LOG_INF("Transport connected");
        } else {
            LOG_INF("Transport disconnected");
        }
        
        // Log total mic buffer bytes processed, GATT notify count, broadcast count, and write_to_tx_queue count
        LOG_INF("Total mic buffer bytes: %u, GATT notify count: %u, Broadcast count: %u, TX queue writes: %u", 
                total_mic_buffer_bytes, gatt_notify_count, broadcast_audio_count, write_to_tx_queue_count);
        
        k_msleep(1000);
	}

    printk("Exiting omi2...");
	return 0;
}
