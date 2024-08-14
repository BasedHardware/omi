#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include "controls.h"
#include "utils.h"
#include "deep_sleep.h"

#define LONG_PRESS_DURATION_MS 3000 // 3 seconds long press to enter deep sleep mode

static button_handler button_cb = NULL;
static struct gpio_callback button_cb_data;
static void cooldown_expired(struct k_work *work);
static void long_press_detected(struct k_work *work);

static K_WORK_DELAYABLE_DEFINE(cooldown_work, cooldown_expired);
static K_WORK_DELAYABLE_DEFINE(long_press_work, long_press_detected);

static const struct device *button_devices[] = {
    DEVICE_DT_GET(DT_NODELABEL(button0)),
    DEVICE_DT_GET(DT_NODELABEL(button1)),
    DEVICE_DT_GET(DT_NODELABEL(button2)),
};

void button_pressed(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    k_work_reschedule(&cooldown_work, K_MSEC(15));
    k_work_reschedule(&long_press_work, K_MSEC(LONG_PRESS_DURATION_MS));
}

static void cooldown_expired(struct k_work *work)
{
    ARG_UNUSED(work);
    for (size_t i = 0; i < ARRAY_SIZE(button_devices); i++) {
        int val = gpio_pin_get(button_devices[i], DT_GPIO_PIN(DT_ALIAS(button0), gpios));
        if (val && button_cb)
        {
            button_cb();
            return;
        }
    }
}

// Deep sleep mode functionality added
static void long_press_detected(struct k_work *work)
{
    ARG_UNUSED(work);
    for (size_t i = 0; i < ARRAY_SIZE(button_devices); i++) {
        int val = gpio_pin_get(button_devices[i], DT_GPIO_PIN(DT_ALIAS(button0), gpios));
        if (val)
        {
            enter_deep_sleep();
            return;
        }
    }
}

int start_controls()
{
    for (size_t i = 0; i < ARRAY_SIZE(button_devices); i++) {
        if (!device_is_ready(button_devices[i])) {
            return -ENODEV;
        }

        int pin = DT_GPIO_PIN(DT_ALIAS(button0), gpios);
        if (gpio_pin_configure(button_devices[i], pin, GPIO_INPUT | GPIO_PULL_UP)) {
            return -EIO;
        }

        gpio_init_callback(&button_cb_data, button_pressed, BIT(pin));
        if (gpio_add_callback(button_devices[i], &button_cb_data)) {
            return -EIO;
        }

        if (gpio_pin_interrupt_configure(button_devices[i], pin, GPIO_INT_EDGE_BOTH)) {
            return -EIO;
        }
    }

    return 0;
}

void set_button_handler(button_handler _handler)
{
    button_cb = _handler;
}
