#pragma once
#include <zephyr/logging/log.h>
#include <zephyr/bluetooth/gatt.h>

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

// #define WAIT_LOG k_sleep(K_MSEC(200));
// #define WAIT_LOG do {} while(0);
// #define WAIT_LOG z_impl_log_process()
// #define WAIT_LOG while (z_impl_log_process() == true) { }