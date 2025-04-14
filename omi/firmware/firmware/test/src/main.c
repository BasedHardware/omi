#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/pm/device_runtime.h>
#include "mic.h"
#include "spi_flash.h"
#include "sd.h"
#include "button.h"
#include "battery.h"

static const struct device *const buttons = DEVICE_DT_GET(DT_ALIAS(buttons));

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
	return 0;
}

int main(void)
{
	struct input_event evt;
	int ret;
	bool button_pressed = false;
	if (init_module() < 0)
	{
		shell_execute_cmd(NULL, "sys off");
		return -1;
	}
	shell_execute_cmd(NULL, "ble on");
	printk("Starting omi2 EVT test...\n");

	ret = pm_device_runtime_get(buttons);
	if (ret < 0) {
		printk("Failed to get device (%d)", ret);
		shell_execute_cmd(NULL, "sys off");
		return 0;
	}

	k_msgq_purge(&input_button);

	while (1) {

		ret = k_msgq_get(&input_button, &evt, K_SECONDS(60));
		if (ret == -EAGAIN) {
			if (!button_pressed && !is_charging)
				shell_execute_cmd(NULL, "sys off");
            continue;
		}

		switch (evt.code) {
		case INPUT_KEY_ENTER:
			if (evt.value == 1) {
				printk("usr button pressed");
				shell_execute_cmd(NULL, "motor on");
				shell_execute_cmd(NULL, "led on 0");
				// shell_execute_cmd(NULL, "led on 1");
				shell_execute_cmd(NULL, "led on 2");
				button_pressed = true;
			} else {
				printk("usr button released");
				shell_execute_cmd(NULL, "motor off");
				shell_execute_cmd(NULL, "led off 0");
				// shell_execute_cmd(NULL, "led off 1");
				shell_execute_cmd(NULL, "led off 2");
				button_pressed = false;
			}
			break;
		}
	}

	ret = pm_device_runtime_put(buttons);
	if (ret < 0) {
		printk("Failed to put device (%d)", ret);
		shell_execute_cmd(NULL, "sys off");
		return 0;
	}
	
	shell_execute_cmd(NULL, "sys off");
	return 0;
}
