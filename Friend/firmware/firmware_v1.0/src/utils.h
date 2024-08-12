#pragma once
#include <zephyr/logging/log.h>
#include <zephyr/bluetooth/gatt.h>

#define ASSERT_OK(result)                                          \
    if ((result) < 0)                                              \
    {                                                              \
        LOG_ERR("Error at %s:%d:%d", __FILE__, __LINE__, result); \
        return (result);                                           \
    }

#define ASSERT_TRUE(result)                                        \
    if (!result)                                                   \
    {                                                              \
        LOG_ERR("Error at %s:%d:%d", __FILE__, __LINE__, result); \
        return -1;                                                 \
    }
