#include <zephyr/kernel.h>
//#include "lib/sdcard/sdcard.h"
#include <zephyr/logging/log.h>
#include "transport.h"
#include "storage.h"
#include "mic.h"
#include "utils.h"
#include "led.h"
#include "config.h"
#include "audio.h"
#include "codec.h"

static void codec_handler(uint8_t *data, size_t len)
{
	broadcast_audio_packets(data, len); // Errors are logged inside
}

static void mic_handler(int16_t *buffer)
{
	codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES); // Errors are logged inside
}

void bt_ctlr_assert_handle(char *name, int type)
{
	if (name != NULL)
	{
		printk("Bt assert-> %s", name);
	}
}

// Main loop
int main(void)
{
	// Led start
	ASSERT_OK(led_start());
	set_led_blue(true);

	// Storage start
	ASSERT_OK(init_storage())

	// Transport start
	ASSERT_OK(transport_start());

	// Codec start
	set_codec_callback(codec_handler);
	ASSERT_OK(codec_start());

	// Mic start
	set_mic_callback(mic_handler);
	ASSERT_OK(mic_start());

	// Blink LED
	bool is_on = true;
	//set_led_blue(false);
	set_led_red(is_on);


	/* SD CARD TEST */
	//int ret = 0;
	/** SD card mount test **/
	/*
	if (mount_sd_card()) {
		printk("Failed to mount SD card\n");
		//return -1;
	} else {
		printk("Successfully mounted SD card\n");
	}

	create_file("audio/test.txt");
	WriteParams params = {"hola", true};
	write_file(params);
	read_file();
	create_file("audio/test1.txt");
	WriteParams params1 = {"mundo", true};
	write_file(params1);
	read_file();
	create_file("audio/test2.txt");
	WriteParams params2 = {"esto es una prueba", true};
	write_file(params2);
	read_file();*/
	/* SD CARD TEST */



	while (1)
	{
		is_on = !is_on;
		set_led_red(is_on);
		k_msleep(500);
	}

	// Unreachable
	return 0;
}
