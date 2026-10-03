#ifndef Z_STUB_GPIO_H
#define Z_STUB_GPIO_H

#include <stdint.h>
#include <zephyr/device.h>

struct gpio_dt_spec {
    const struct device *port;
    uint8_t pin;
    uint32_t dt_flags;
};

#define GPIO_DT_SPEC_GET_OR(node_id, prop, default_value) {.port = &z_stub_dev_gpio1, .pin = 11, .dt_flags = 0}
#define GPIO_DISCONNECTED 0x1
#define GPIO_OUTPUT 0x2

int gpio_pin_configure(const struct device *port, uint32_t pin, uint32_t flags);
int gpio_pin_configure_dt(const struct gpio_dt_spec *spec, uint32_t extra_flags);
int gpio_pin_set_dt(const struct gpio_dt_spec *spec, int value);
int gpio_pin_set_raw(const struct device *port, uint32_t pin, int value);

#endif
