/**
 * @file utils.h
 * @brief Utility macros for error handling and assertion
 * 
 * This file contains common macros used throughout the codebase for
 * standardized error handling and assertions, helping with code readability
 * and maintainability.
 */
#ifndef UTILS_H
#define UTILS_H

#include <zephyr/logging/log.h>
#include <zephyr/bluetooth/gatt.h>

/**
 * @brief Assert that a function call returns a non-negative value
 * 
 * Checks if the result of an operation is negative (indicating an error).
 * If an error is detected, logs the error with file and line information,
 * and returns the error code to the caller.
 * 
 * @param result The result value to check (expected to be >= 0)
 */
#define ASSERT_OK(result)                                          \
    if ((result) < 0)                                              \
    {                                                              \
        LOG_ERR("Error at %s:%d:%d", __FILE__, __LINE__, result); \
        return (result);                                           \
    }

/**
 * @brief Assert that a condition is true
 * 
 * Checks if a condition evaluates to true. If the condition is false,
 * logs the error with file and line information, and returns -1
 * to indicate failure to the caller.
 * 
 * @param result The condition to check (expected to be true)
 */
#define ASSERT_TRUE(result)                                        \
    if (!result)                                                   \
    {                                                              \
        LOG_ERR("Error at %s:%d:%d", __FILE__, __LINE__, result); \
        return -1;                                                 \
    }

#endif