#ifndef TEST_KERNEL_H
#define TEST_KERNEL_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define ARG_UNUSED(x) (void) (x)
#define printk(...) ((void) 0)
int64_t k_uptime_get(void);
#endif
