#include <zephyr/drivers/gpio.h>
#include <zephyr/dt-bindings/gpio/nordic-nrf-gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/pm/device_runtime.h>
#include <zephyr/shell/shell.h>

#include "battery.h"
#include "button.h"
#include "mic.h"
#include "sd.h"
#include "spi_flash.h"

static const struct device *const buttons = DEVICE_DT_GET(DT_ALIAS(buttons));
static const struct gpio_dt_spec rfsw_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(rfsw_en_pin), gpios, {0});
static int init_module(void)
{
    int ret;
    ret = mic_init();
    if (ret < 0) {
        printk("Failed to initialize mic module (%d)\n", ret);
    }

    ret = flash_init();
    if (ret < 0) {
        printk("Failed to initialize flash module (%d)\n", ret);
    }

    ret = app_sd_init();
    if (ret < 0) {
        printk("Failed to initialize sd module (%d)\n", ret);
    }

    ret = bat_init();
    if (ret < 0) {
        printk("Failed to initialize battery module (%d)\n", ret);
    }

    gpio_pin_configure_dt(&rfsw_en, (GPIO_OUTPUT | NRF_GPIO_DRIVE_S0H1));
    gpio_pin_set_dt(&rfsw_en, 1);
    return 0;
}

int main(void)
{
    struct input_event evt;
    int ret;
    bool button_pressed = false;
    if (init_module() < 0) {
        printk("Failed to initialize modules\n");
        return -1;
    }

    // Start shell over UART
    const struct shell *shell_ptr = shell_backend_uart_get_ptr();
    if (shell_ptr) {
        ret = shell_start(shell_ptr);
        if (ret < 0) {
            printk("Failed to start shell (%d)\n", ret);
        }
    } else {
        printk("UART shell backend not found.\n");
    }

    printk("Starting omi EVT test...\n");

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
            // if (!button_pressed && !is_charging)
            // 	shell_execute_cmd(NULL, "sys off");
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
