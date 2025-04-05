#include <stdio.h>
#include <zephyr/kernel.h>
#include <stdlib.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/shell/shell.h>

static const struct gpio_dt_spec led_red = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(led_red), gpios, {0});
static const struct gpio_dt_spec led_green = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(led_green), gpios, {0});
static const struct gpio_dt_spec led_blue = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(led_blue), gpios, {0});

static int led_control(int led_num, int state)
{
    int ret;
    const struct gpio_dt_spec *led_spec;
    switch (led_num)
    {
    case 0:
        led_spec = &led_red;
        break;
    case 1:
        led_spec = &led_green;
        break;
    case 2:
        led_spec = &led_blue;
        break;
    default:
        return -EINVAL;
    }

    ret = gpio_pin_configure_dt(led_spec, GPIO_OUTPUT);
    if (ret < 0)
    {
        return ret;
    }

    ret = gpio_pin_set_dt(led_spec, state);
    if (ret < 0)
    {
        return ret;
    }

    return 0;
}

static int cmd_led_on(const struct shell *shell, size_t argc, char **argv)
{
    int ret;
    if (argc < 2)
    {
        shell_error(shell, "Usage: %s <led_num>", argv[0]);
        return -EINVAL;
    }

    ret = led_control(atoi(argv[1]), 1);
    if (ret < 0)
    {
        shell_error(shell, "Failed to turn on LED %d (%d)", atoi(argv[1]), ret);
        return ret;
    }

    return 0;
}

static int cmd_led_off(const struct shell *shell, size_t argc, char **argv)
{
    int ret;
    if (argc < 2)
    {
        shell_error(shell, "Usage: %s <led_num>", argv[0]);
        return -EINVAL;
    }

    ret = led_control(atoi(argv[1]), 0);
    if (ret < 0)
    {
        shell_error(shell, "Failed to turn off LED %d (%d)", atoi(argv[1]), ret);
        return ret;
    }

    return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_led_cmds,
                               SHELL_CMD_ARG(on, NULL, "Turn on LED", cmd_led_on, 2, 0),
                               SHELL_CMD_ARG(off, NULL, "Turn off LED", cmd_led_off, 2, 0),
                               SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(led, &sub_led_cmds, "led", NULL);