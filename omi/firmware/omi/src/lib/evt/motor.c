#include <zephyr/logging/log.h>
#include <zephyr/shell/shell.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h> 

static const struct gpio_dt_spec motor =
   GPIO_DT_SPEC_GET_OR(DT_NODELABEL(motor_pin), gpios, {0});

static struct k_work_delayable motor_off_work;

static void motor_off_work_handler(struct k_work *work)
{
    gpio_pin_set_dt(&motor, 0);
}

static int cmd_motor_on(const struct shell *shell, size_t argc, char **argv)
{
    shell_print(shell, "motor on\n");
    gpio_pin_configure_dt(&motor, GPIO_OUTPUT);
    gpio_pin_set_dt(&motor, 1);

    // schedule the delayable work to turn off motor after 100ms
    k_work_schedule(&motor_off_work, K_MSEC(100));

    return 0;
}

static int cmd_motor_off(const struct shell *shell, size_t argc, char **argv)
{
    shell_print(shell, "motor off\n");
    gpio_pin_configure_dt(&motor, GPIO_OUTPUT);
    gpio_pin_set_dt(&motor, 0);

    // remove the delayable work if it is scheduled
    k_work_cancel_delayable(&motor_off_work);

    return 0;
}

static void motor_init(void)
{
    k_work_init_delayable(&motor_off_work, motor_off_work_handler);
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_motor_cmds,
                               SHELL_CMD_ARG(on, NULL, "Turn on motor", cmd_motor_on, 1, 0),
                               SHELL_CMD_ARG(off, NULL, "Turn off motor", cmd_motor_off, 1, 0),
                               SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(motor, &sub_motor_cmds, "motor", NULL);

SYS_INIT(motor_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);