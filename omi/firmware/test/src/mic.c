#include <stdio.h>
#include <stdlib.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/audio/dmic.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/util.h>

#define BITS_PER_BYTE 8

#define SAMPLE_RATE_HZ 16000
#define SAMPLE_BITS 16
#define CHANNEL_COUNT 2
 #define TIMEOUT_MS 2000
 #define CAPTURE_MS 1000
 #define BLOCK_SIZE ((SAMPLE_BITS / BITS_PER_BYTE) * (SAMPLE_RATE_HZ * CAPTURE_MS) / 1000) * CHANNEL_COUNT
 #define BLOCK_COUNT 2

static const struct device *const dmic = DEVICE_DT_GET(DT_ALIAS(dmic0));
static const struct gpio_dt_spec mic_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_en_pin), gpios, {0});
static const struct gpio_dt_spec mic_thsel = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_thsel_pin), gpios, {0});
static const struct gpio_dt_spec mic_wake = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_wake_pin), gpios, {0});

K_MEM_SLAB_DEFINE_STATIC(mem_slab, BLOCK_SIZE, BLOCK_COUNT, 4);

static struct pcm_stream_cfg stream = {
	.pcm_rate = SAMPLE_RATE_HZ,
	.pcm_width = SAMPLE_BITS,
	.block_size = BLOCK_SIZE,
	.mem_slab = &mem_slab,
};

static struct dmic_cfg cfg = {
	.io =
		{
			.min_pdm_clk_freq = 1000000,
			.max_pdm_clk_freq = 3500000,
			.min_pdm_clk_dc = 40,
			.max_pdm_clk_dc = 60,
		},
	.streams = &stream,
	.channel =
		{
			.req_num_streams = 1,
			.req_num_chan = CHANNEL_COUNT,
		},
};

static bool initialized;

static int cmd_mic_capture(const struct shell *sh, size_t argc, char **argv)
{
	int ret, time = 1;
	void *buffer = NULL;
	uint32_t size;

	if (argc > 1)
	{
		char *endptr;
		time = strtol(argv[1], &endptr, 10);
		if (*endptr != '\0' || time <= 0)
		{
			shell_error(sh, "Invalid time argument");
			return -EINVAL;
		}
		time *= (1000 / CAPTURE_MS);
	}

	if (!initialized)
	{
		shell_error(sh, "Microphone module not initialized");
		return -EPERM;
	}

	// Configure and enable microphone pins
	mic_power_on();
	
	shell_print(sh, "S");
	ret = dmic_configure(dmic, &cfg);
	if (ret < 0)
	{
		shell_error(sh, "Failed to configure DMIC(%d)", ret);
		goto cleanup;
	}

	for (int i = 0; i < time; i++)
	{
		ret = dmic_trigger(dmic, DMIC_TRIGGER_START);
		if (ret < 0)
		{
			shell_error(sh, "START trigger failed (%d)", ret);
			goto cleanup;
		}
		
		ret = dmic_read(dmic, 0, &buffer, &size, TIMEOUT_MS);
		if (ret < 0)
		{
			shell_error(sh, "DMIC read failed (%d)", ret);
			dmic_trigger(dmic, DMIC_TRIGGER_STOP);
			goto cleanup;
		}

		// Process captured data
		for (int j = 0; j < size / sizeof(int16_t); j++)
		{
			shell_print(sh, "%d", ((int16_t *)buffer)[j]);
		}

		k_mem_slab_free(&mem_slab, buffer);
		buffer = NULL;
		ret = dmic_trigger(dmic, DMIC_TRIGGER_STOP);
		if (ret < 0)
		{
			shell_error(sh, "STOP trigger failed (%d)", ret);
		}
	}

cleanup:
	if (buffer)
	{
		k_mem_slab_free(&mem_slab, buffer);
	}
	shell_print(sh, "E");
	mic_power_off();

	return ret;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_mic_cmds,
							   SHELL_CMD(capture, NULL, "Capture microphone data", cmd_mic_capture),
							   SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(mic, &sub_mic_cmds, "Microphone", NULL);

int mic_power_off(void)
{
	gpio_pin_configure_dt(&mic_thsel, GPIO_OUTPUT);
	gpio_pin_set_dt(&mic_thsel, 0);
	gpio_pin_configure_dt(&mic_wake, GPIO_INPUT);
	gpio_pin_configure_dt(&mic_en, GPIO_OUTPUT);
	gpio_pin_set(mic_en.port, mic_en.pin, 0);
	return 0;
}

int mic_power_on(void)
{
	gpio_pin_configure_dt(&mic_thsel, GPIO_OUTPUT);
	gpio_pin_set_dt(&mic_thsel, 1);
	gpio_pin_configure_dt(&mic_wake, GPIO_INPUT);
	gpio_pin_configure_dt(&mic_en, GPIO_OUTPUT);
	gpio_pin_set_dt(&mic_en, 1);
	return 0;
}

int mic_init(void)
{
	if (!device_is_ready(dmic))
	{
		return -ENODEV;
	}

	mic_power_off();

	cfg.channel.req_chan_map_lo = dmic_build_channel_map(0, 0, PDM_CHAN_LEFT) | 
	dmic_build_channel_map(1, 0, PDM_CHAN_RIGHT);

	initialized = true;

	return 0;
}
