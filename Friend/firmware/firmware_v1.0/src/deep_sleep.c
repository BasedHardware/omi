// src/deep_sleep.c
#include <zephyr/kernel.h>
#include <hal/nrf_power.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/pm/device.h>
#include <zephyr/pm/policy.h>

#include "deep_sleep.h"
#include "led.h"

#define BUTTON_PIN 4

static const struct device *button_device;

void configure_button_for_wake_up(void) {
    // Use nRF GPIO configuration for wake-up in System OFF mode
    nrf_gpio_cfg_sense_input(BUTTON_PIN, NRF_GPIO_PIN_PULLUP, NRF_GPIO_PIN_SENSE_LOW);
}

void initialize_button_device(void) {
    button_device = DEVICE_DT_GET(DT_ALIAS(sw0)); // Assuming 'sw0' is correctly defined

    if (!device_is_ready(button_device)) {
        printk("Error: Button device not ready\n");
        return;
    }

    // Configure the button GPIO as input with pull-up
    gpio_pin_configure(button_device, BUTTON_PIN, GPIO_INPUT | GPIO_PULL_UP);
}

void enable_button_wakeup(void) {
    if (button_device) {
        int ret = pm_device_wakeup_enable(button_device, true);
        if (ret != 0) {
            printk("Error enabling wake-up: %d\n", ret);
        }
    }
}

void enter_deep_sleep(void) {
    // Prepare system for deep sleep
    configure_button_for_wake_up();

    set_led_green(true);

    // Actions to take before entering deep sleep mode here
    k_sleep(K_SECONDS(1));
    
    // Use Zephyr's power management API to enter deep sleep mode (PM_STATE_SOFT_OFF)
    pm_state_force(0, &(struct pm_state_info){PM_STATE_SOFT_OFF, 0, 0});
}

// Call these functions to initialize and use wake-up
void prepare_for_deep_sleep(void) {
    initialize_button_device();
    enable_button_wakeup();
}
