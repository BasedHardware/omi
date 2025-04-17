#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device_runtime.h>
#include "lib/evt/mic.h"
#include "lib/dk2/mic.h"
#include "lib/dk2/codec.h"
#include "lib/dk2/config.h"
LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

static void codec_handler(uint8_t *data, size_t len)
{
    LOG_INF("Codec handler received %d bytes of data: [%02x %02x %02x %02x %02x]", 
            len, 
            len > 0 ? data[0] : 0, 
            len > 1 ? data[1] : 0, 
            len > 2 ? data[2] : 0, 
            len > 3 ? data[3] : 0, 
            len > 4 ? data[4] : 0);
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
        k_msleep(500);
	}

    printk("Exiting omi2...");
	return 0;
}
