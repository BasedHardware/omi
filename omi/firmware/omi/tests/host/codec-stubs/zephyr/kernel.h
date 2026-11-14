#pragma once
#include <stddef.h>
#include <stdint.h>
struct k_thread {
    int unused;
};
typedef void (*k_thread_entry_t)(void);
#define K_SEM_DEFINE(n, a, b) int n
#define K_THREAD_STACK_DEFINE(n, s) char n[s]
#define K_THREAD_STACK_SIZEOF(n) sizeof(n)
#define K_FOREVER 0
#define K_NO_WAIT 0
#define K_PRIO_PREEMPT(n) n
#define __ALIGN(n) __attribute__((aligned(n)))
static int thread_calls;
static inline void k_sem_give(int *s)
{
    (void) s;
}
static inline void k_sem_take(int *s, int t)
{
    (void) s;
    (void) t;
}
#define k_thread_create(...) (++thread_calls)
