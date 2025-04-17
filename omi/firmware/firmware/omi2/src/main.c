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

static void codec_handler(uint8_t *data, size_t len)
{
    int err = broadcast_audio_packets(data, len);
    if (err)
    {
        //LOG_ERR("Failed to broadcast audio packets: %d", err);
    }
}

static void mic_handler(int16_t *buffer)
{
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
        
        // Update connection status in logs
        if (is_connected) {
            LOG_INF("Transport connected");
        } else {
            LOG_INF("Transport disconnected");
        }
        
        k_msleep(500);
	}

    printk("Exiting omi2...");
	return 0;
}
