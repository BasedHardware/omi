#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device_runtime.h>
#include "lib/evt/mic.h"
#include "lib/evt/spi_flash.h"
#include "lib/evt/sd.h"
#include "lib/evt/button.h"
#include "lib/evt/battery.h"
#include "lib/dk2/transport.h"
#include "lib/dk2/codec.h"
#include "lib/dk2/utils.h"
LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

static void codec_handler(uint8_t *data, size_t len)
{
    int err = broadcast_audio_packets(data, len);
    if (err)
    {
        LOG_ERR("Failed to broadcast audio packets: %d", err);
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

static int init_module(void)
{
	int ret;
	ret = mic_init();
	if (ret < 0)
	{
		printk("Failed to initialize mic module (%d)\n", ret);
	}

	ret = flash_init();
	if (ret < 0)
	{
		printk("Failed to initialize flash module (%d)\n", ret);
	}

	ret = app_sd_init();
	if (ret < 0)
	{
		printk("Failed to initialize sd module (%d)\n", ret);
	}

	ret = bat_init();
	if (ret < 0)
	{
		printk("Failed to initialize battery module (%d)\n", ret);
	}
	return 0;
}

int main(void)
{
	int ret;
	if (init_module() < 0)
	{
		return -1;
	}

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
	
	// Initialize transport
	LOG_INF("Initializing transport...\n");
	ret = transport_start();
	if (ret)
	{
		LOG_ERR("Failed to start transport (err %d)", ret);
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
