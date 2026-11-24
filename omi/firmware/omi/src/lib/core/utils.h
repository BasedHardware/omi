#ifndef UTILS_H
#define UTILS_H

#include <zephyr/bluetooth/gatt.h>
#include <zephyr/logging/log.h>

#define ASSERT_OK(result)                                                                                              \
    if ((result) < 0) {                                                                                                \
        LOG_ERR("Error at %s:%d:%d", __FILE__, __LINE__, result);                                                      \
        return (result);                                                                                               \
    }

#define ASSERT_TRUE(result)                                                                                            \
    do {                                                                                                               \
        const int omi_assert_true_value_ = !!(result);                                                                 \
        if (!omi_assert_true_value_) {                                                                                 \
            LOG_ERR("Error at %s:%d:%d", __FILE__, __LINE__, omi_assert_true_value_);                                  \
            return -1;                                                                                                 \
        }                                                                                                              \
    } while (0)

#endif