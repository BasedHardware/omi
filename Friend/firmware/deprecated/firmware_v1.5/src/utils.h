#pragma once
#include <zephyr/logging/log.h>
#include <zephyr/bluetooth/gatt.h>

static const struct device *gpio0_port = DEVICE_DT_GET(DT_NODELABEL(gpio0));
static const struct device *gpio1_port = DEVICE_DT_GET(DT_NODELABEL(gpio1));

#define ASSERT_OK(result)                                          \
    if ((result) < 0)                                              \
    {                                                              \
        printk("Error at %s:%d:%d\n", __FILE__, __LINE__, result); \
        return (result);                                           \
    }

#define ASSERT_TRUE(result)                                        \
    if (!result)                                                   \
    {                                                              \
        printk("Error at %s:%d:%d\n", __FILE__, __LINE__, result); \
        return -1;                                                 \
    }
