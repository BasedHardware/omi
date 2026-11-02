#include <assert.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#define ATOMIC_INIT(v) (v)
typedef int atomic_t;
#define ARG_UNUSED(x) (void) (x)
#define K_FOREVER 0
#define LOG_INF(...)
#define K_SEM_DEFINE(name, initial, limit) static int name = initial
#define K_THREAD_DEFINE(name, stack, fn, p1, p2, p3, priority, options, delay)                                         \
    static void (*name)(void *, void *, void *) = fn
static jmp_buf finished;
static unsigned gives, delays, shutdowns;
static int atomic_get(int *v)
{
    return *v;
}
static bool atomic_cas(int *v, int old, int newval)
{
    if (*v != old)
        return false;
    *v = newval;
    return true;
}
static void k_sem_give(int *s)
{
    *s = 1;
    gives++;
}
static void k_sem_take(int *s, int t)
{
    (void) t;
    if (!*s)
        longjmp(finished, 1);
    *s = 0;
}
static void k_msleep(int n)
{
    assert(n == 50);
    delays++;
}
static void turnoff_all(void)
{
    shutdowns++;
}
#include "power_off.inc"
int main(void)
{
    assert(!power_control_off_pending());
    assert(power_control_schedule_off() == 0);
    assert(power_control_schedule_off() == 0 && gives == 1 && shutdowns == 0);
    assert(power_control_off_pending());
    if (setjmp(finished) == 0)
        power_off_thread(NULL, NULL, NULL);
    assert(delays == 1 && shutdowns == 1);
    puts("production shutdown worker queues once, defers, and calls orderly shutdown passed");
}
