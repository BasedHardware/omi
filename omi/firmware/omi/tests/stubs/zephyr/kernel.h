#ifndef Z_STUB_KERNEL_H
#define Z_STUB_KERNEL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>

typedef struct {
    int64_t ticks;
} k_timeout_t;

#define K_NO_WAIT ((k_timeout_t) {0})
#define K_FOREVER ((k_timeout_t) {-1})
#define K_MSEC(ms) ((k_timeout_t) {(ms)})
#define K_PRIO_PREEMPT(p) (p)

extern int64_t z_stub_now_ms;

static inline int64_t k_uptime_get(void)
{
    return z_stub_now_ms;
}
static inline void k_msleep(int32_t ms)
{
    if (ms > 0) {
        z_stub_now_ms += ms;
    }
}
static inline void k_sleep(k_timeout_t t)
{
    if (t.ticks > 0) {
        z_stub_now_ms += t.ticks;
    }
}
static inline void k_yield(void) {}

struct k_sem {
    unsigned int count;
    unsigned int limit;
};

#define K_SEM_DEFINE(name, initial_count, count_limit)                                                                 \
    struct k_sem name = {.count = (initial_count), .limit = (count_limit)}

static inline void k_sem_init(struct k_sem *sem, unsigned int initial_count, unsigned int limit)
{
    sem->count = initial_count;
    sem->limit = limit;
}
static inline int k_sem_take(struct k_sem *sem, k_timeout_t timeout)
{
    ARG_UNUSED(timeout);
    if (sem->count > 0) {
        sem->count--;
        return 0;
    }
    return -EBUSY;
}
static inline void k_sem_give(struct k_sem *sem)
{
    if (sem->count < sem->limit) {
        sem->count++;
    }
}

struct k_msgq {
    uint8_t *buf;
    size_t msg_size;
    uint32_t max_msgs;
    uint32_t head;
    uint32_t used;
};

#define K_MSGQ_DEFINE(name, q_msg_size, q_max_msgs, q_align)                                                           \
    static uint8_t name##_buf[(q_max_msgs) * (q_msg_size)];                                                            \
    struct k_msgq name = {.buf = name##_buf, .msg_size = (q_msg_size), .max_msgs = (q_max_msgs)}

static inline int k_msgq_put(struct k_msgq *q, const void *data, k_timeout_t timeout)
{
    if (q->used >= q->max_msgs) {
        if (timeout.ticks > 0) {
            z_stub_now_ms += timeout.ticks;
        }
        return -ENOMEM;
    }
    uint32_t tail = (q->head + q->used) % q->max_msgs;
    memcpy(q->buf + (size_t) tail * q->msg_size, data, q->msg_size);
    q->used++;
    return 0;
}
static inline int k_msgq_get(struct k_msgq *q, void *data, k_timeout_t timeout)
{
    if (q->used == 0) {
        if (timeout.ticks > 0) {
            z_stub_now_ms += timeout.ticks;
        }
        return -EAGAIN;
    }
    memcpy(data, q->buf + (size_t) q->head * q->msg_size, q->msg_size);
    q->head = (q->head + 1) % q->max_msgs;
    q->used--;
    return 0;
}
static inline uint32_t k_msgq_num_used_get(struct k_msgq *q)
{
    return q->used;
}

typedef void (*k_thread_entry_t)(void *, void *, void *);
typedef struct k_thread *k_tid_t;
#define snprintk snprintf

struct k_thread {
    k_thread_entry_t entry;
};

#define K_THREAD_STACK_DEFINE(name, size) static uint8_t name[size]
#define K_THREAD_STACK_SIZEOF(s) sizeof(s)

static inline struct k_thread *k_thread_create(struct k_thread *thread,
                                               void *stack,
                                               size_t stack_size,
                                               k_thread_entry_t entry,
                                               void *p1,
                                               void *p2,
                                               void *p3,
                                               int prio,
                                               uint32_t options,
                                               k_timeout_t delay)
{
    ARG_UNUSED(stack);
    ARG_UNUSED(stack_size);
    ARG_UNUSED(prio);
    ARG_UNUSED(options);
    ARG_UNUSED(delay);
    thread->entry = entry;
    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);
    return thread;
}
static inline int k_thread_name_set(struct k_thread *thread, const char *name)
{
    ARG_UNUSED(thread);
    ARG_UNUSED(name);
    return 0;
}

struct k_spinlock {
    int dummy;
};
typedef int k_spinlock_key_t;
static inline k_spinlock_key_t k_spin_lock(struct k_spinlock *lock)
{
    ARG_UNUSED(lock);
    return 0;
}
static inline void k_spin_unlock(struct k_spinlock *lock, k_spinlock_key_t key)
{
    ARG_UNUSED(lock);
    ARG_UNUSED(key);
}

#endif
