#ifndef TEST_KERNEL_H
#define TEST_KERNEL_H
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define K_MUTEX_DEFINE(name) pthread_mutex_t name = PTHREAD_MUTEX_INITIALIZER
#define K_FOREVER (-1)
static inline int k_mutex_lock(pthread_mutex_t *mutex, int timeout)
{
    (void) timeout;
    return pthread_mutex_lock(mutex);
}
static inline int k_mutex_unlock(pthread_mutex_t *mutex)
{
    return pthread_mutex_unlock(mutex);
}
#define ARG_UNUSED(x) (void) (x)
#define printk(...) ((void) 0)
int64_t k_uptime_get(void);
#endif
