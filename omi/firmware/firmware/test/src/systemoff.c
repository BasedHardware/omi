#include <inttypes.h>
#include <stdio.h>

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/pm/device.h>
#include <zephyr/sys/poweroff.h>
#include <zephyr/sys/util.h>
#include <zephyr/shell/shell.h>
#include <zephyr/drivers/wifi/nrf_wifi/bus/rpu_hw_if.h>
static const struct gpio_dt_spec usr_btn = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(usr_btn), gpios, {0});

 static int cmd_sys_off(const struct shell *sh, size_t argc, char **argv)
 {
     int rc;
#if defined(CONFIG_CONSOLE)
     const struct device *const cons = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));

     if (!device_is_ready(cons))
     {
         shell_error(sh, "%s: device not ready.\n", cons->name);
         return 0;
     }
#endif
#if defined(CONFIG_WIFI)
    rpu_disable();
#endif

     shell_print(sh, "\n%s system off demo\n", CONFIG_BOARD);

     /* configure usr_btn as input, interrupt as level active to allow wake-up */
     rc = gpio_pin_configure_dt(&usr_btn, GPIO_INPUT);
     if (rc < 0)
     {
         shell_error(sh, "Could not configure usr_btn GPIO (%d)\n", rc);
         return 0;
     }

     rc = gpio_pin_interrupt_configure_dt(&usr_btn, GPIO_INT_LEVEL_LOW);
     if (rc < 0)
     {
         shell_error(sh, "Could not configure usr_btn GPIO interrupt (%d)\n", rc);
         return 0;
     }

     shell_print(sh, "Entering system off; press usr_btn to restart\n");
#if defined(CONFIG_CONSOLE)
     rc = pm_device_action_run(cons, PM_DEVICE_ACTION_SUSPEND);
     if (rc < 0)
     {
         shell_error(sh, "Could not suspend console (%d)\n", rc);
         return 0;
     }
#endif
     sys_poweroff();

     return 0;
 }

 SHELL_STATIC_SUBCMD_SET_CREATE(sub_systemoff_cmds,
                                SHELL_CMD(off, NULL, "System off", cmd_sys_off),
                                SHELL_SUBCMD_SET_END);

 SHELL_CMD_REGISTER(sys, &sub_systemoff_cmds, "System off", NULL);