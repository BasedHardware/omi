#include <errno.h>

#include "button.h"
#include <zephyr/kernel.h>
#include <zephyr/pm/device_runtime.h>
#include <zephyr/shell/shell.h>

static const struct device *const buttons = DEVICE_DT_GET(DT_ALIAS(buttons));
K_MSGQ_DEFINE(input_button, sizeof(struct input_event), 10, 1);

static void buttons_input_cb(struct input_event *evt, void *user_data)
{
	ARG_UNUSED(user_data);

	(void)k_msgq_put(&input_button, evt, K_NO_WAIT);
}

INPUT_CALLBACK_DEFINE(buttons, buttons_input_cb, NULL);

static int cmd_buttons_check(const struct shell *sh, size_t argc, char **argv)
{
	int ret;

	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	ret = pm_device_runtime_get(buttons);
	if (ret < 0) {
		shell_error(sh, "Failed to get device (%d)", ret);
		return 0;
	}

	k_msgq_purge(&input_button);

	while (1) {
		int ret;
		struct input_event evt;

		ret = k_msgq_get(&input_button, &evt, K_SECONDS(5));
		if (ret == -EAGAIN) {
			shell_error(sh, "No input received");
			return 0;

		}

		switch (evt.code) {
		case INPUT_KEY_ENTER:
			if (evt.value == 1) {
				shell_print(sh, "usr button pressed");

			} else {
				shell_print(sh, "usr button released");
			}
			break;
		}
	}

	ret = pm_device_runtime_put(buttons);
	if (ret < 0) {
		shell_error(sh, "Failed to put device (%d)", ret);
		return 0;
	}

	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_buttons_cmds,
			       SHELL_CMD(check, NULL, "Check buttons", cmd_buttons_check),
			       SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(button, &sub_buttons_cmds, "Buttons", NULL);