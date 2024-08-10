#pragma once
#include <zephyr/logging/log.h>
#include <zephyr/bluetooth/gatt.h>
LOG_MODULE_REGISTER(util, CONFIG_LOG_DEFAULT_LEVEL);

#define ASSERT_OK(result)                                          \
    if ((result) < 0)                                              \
    {                                                              \
        LOG_ERR("Error at %s:%d:%d\n", __FILE__, __LINE__, result); \
        return (result);                                           \
    }

#define ASSERT_TRUE(result)                                        \
    if (!result)                                                   \
    {                                                              \
        LOG_ERR("Error at %s:%d:%d\n", __FILE__, __LINE__, result); \
        return -1;                                                 \
    }

// #define WAIT_LOG k_sleep(K_MSEC(200));
// #define WAIT_LOG do {} while(0);
// #define WAIT_LOG z_impl_log_process()
// #define WAIT_LOG while (z_impl_log_process() == true) { }