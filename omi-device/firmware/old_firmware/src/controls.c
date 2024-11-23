#include <zephyr/kernel.h>
#include "controls.h"
#include "utils.h"

static button_handler button_cb = NULL;
static struct gpio_callback button_cb_data;

static void cooldown_expired(struct k_work *work)
{
    ARG_UNUSED(work);
    int val = gpio_pin_get_dt(&button);
    if (val && button_cb)
    {
        button_cb();
    }
}

static K_WORK_DELAYABLE_DEFINE(cooldown_work, cooldown_expired);

void button_pressed(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    k_work_reschedule(&cooldown_work, K_MSEC(15));
}

int start_controls()
{
    ASSERT_OK(gpio_is_ready_dt(&button));
    ASSERT_OK(gpio_pin_configure_dt(&button, GPIO_INPUT));
    gpio_init_callback(&button_cb_data, button_pressed, BIT(button.pin));
    ASSERT_OK(gpio_add_callback(button.port, &button_cb_data));
    ASSERT_OK(gpio_pin_interrupt_configure_dt(&button, GPIO_INT_EDGE_BOTH));

    return 0;
}

void set_button_handler(button_handler _handler)
{
    button_cb = _handler;
}