#ifndef TEST_ZEPHYR_ATOMIC_H
#define TEST_ZEPHYR_ATOMIC_H
#include <stdbool.h>
typedef int atomic_t;
static inline bool atomic_cas(atomic_t *value, int old, int next)
{
    if (*value != old)
        return false;
    *value = next;
    return true;
}
#endif
