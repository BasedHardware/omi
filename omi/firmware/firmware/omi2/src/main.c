#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device_runtime.h>
#include "lib/evt/mic.h"
#include "lib/evt/spi_flash.h"
#include "lib/evt/sd.h"
#include "lib/evt/button.h"
#include "lib/evt/battery.h"
LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

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

	while (1) {
        LOG_INF("Running omi2...\n");
        k_msleep(500);
	}

    printk("Exiting omi2...");
	return 0;
}
