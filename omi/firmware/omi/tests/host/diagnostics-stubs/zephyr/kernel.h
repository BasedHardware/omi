#include <stdint.h>
extern int64_t test_uptime;
static inline int64_t k_uptime_get(void)
{
    return test_uptime;
}
