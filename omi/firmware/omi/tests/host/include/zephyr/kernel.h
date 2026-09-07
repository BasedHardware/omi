#ifndef TEST_ZEPHYR_KERNEL_H
#define TEST_ZEPHYR_KERNEL_H
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

typedef int64_t k_timeout_t;
#define K_NO_WAIT 0
#define K_FOREVER -1
#define K_MSEC(ms) (ms)
#define ARG_UNUSED(value) ((void) (value))
struct k_work {
    int unused;
};
struct k_work_delayable {
    struct k_work work;
    void (*handler)(struct k_work *);
    int64_t due;
};
#define K_WORK_DELAYABLE_DEFINE(name, fn) struct k_work_delayable name = {.handler = fn, .due = INT64_MAX}
struct k_spinlock {
    int locked;
};
typedef int k_spinlock_key_t;
static inline k_spinlock_key_t k_spin_lock(struct k_spinlock *lock)
{
    assert(!lock->locked);
    lock->locked = 1;
    return 0;
}
static inline void k_spin_unlock(struct k_spinlock *lock, k_spinlock_key_t key)
{
    (void) key;
    assert(lock->locked);
    lock->locked = 0;
}
extern int64_t fake_now;
static inline int64_t k_uptime_get(void)
{
    return fake_now;
}
static inline int k_work_reschedule(struct k_work_delayable *work, k_timeout_t delay)
{
    assert(delay >= 0);
    work->due = fake_now + delay;
    return 1;
}
struct k_sem {
    unsigned count;
};
struct k_msgq {
    int items[16];
    unsigned head, count;
};
static inline int k_msgq_put(struct k_msgq *q, const void *item, k_timeout_t timeout)
{
    (void) timeout;
    if (q->count == 16)
        return -ENOMSG;
    q->items[(q->head + q->count++) % 16] = *(const int *) item;
    return 0;
}
static inline int k_msgq_get(struct k_msgq *q, void *item, k_timeout_t timeout)
{
    assert(timeout == K_NO_WAIT);
    if (!q->count)
        return -ENOMSG;
    *(int *) item = q->items[q->head++ % 16];
    --q->count;
    return 0;
}
static inline void k_sem_give(struct k_sem *sem)
{
    sem->count = 1;
}
int k_sem_take(struct k_sem *sem, k_timeout_t timeout);
#endif
