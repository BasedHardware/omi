/* Single-thread host seam. Tests run production mic transitions, not hardware
 * drivers, scheduling, GPIO timing, Bluetooth, or memory barriers under load. */
#ifndef AAD_TEST_KERNEL_H
#define AAD_TEST_KERNEL_H
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

extern int64_t test_now;
extern unsigned test_starts, test_stops, test_freed;
extern int test_wake_level;
struct device {
    const char *name;
};
extern const struct device test_device;
struct rtc_time {
    int unused;
};
struct k_sem {
    unsigned count;
};
struct k_mutex {
    bool locked;
};
#define K_MUTEX_DEFINE(name) struct k_mutex name
static inline int k_mutex_lock(struct k_mutex *m, int64_t timeout)
{
    (void) timeout;
    assert(!m->locked);
    m->locked = true;
    return 0;
}
static inline void k_mutex_unlock(struct k_mutex *m)
{
    assert(m->locked);
    m->locked = false;
}
struct k_thread {
    int unused;
};
struct k_spinlock {
    int unused;
};
struct k_mem_slab {
    int unused;
};
typedef int k_spinlock_key_t;
typedef int64_t k_timeout_t;
typedef int atomic_t;
typedef int atomic_val_t;
#define ATOMIC_INIT(v) (v)
static inline int atomic_get(const atomic_t *v)
{
    return *v;
}
static inline void atomic_set(atomic_t *v, int n)
{
    *v = n;
}
static inline void atomic_clear(atomic_t *v)
{
    *v = 0;
}
static inline void atomic_inc(atomic_t *v)
{
    ++*v;
}
static inline bool atomic_cas(atomic_t *v, int old, int n)
{
    if (*v != old)
        return false;
    *v = n;
    return true;
}
#define ARG_UNUSED(v) ((void) (v))
#define BIT(v) (1U << (v))
#define K_FOREVER (-1)
#define K_NO_WAIT 0
#define K_MSEC(v) (v)
#define K_SEM_DEFINE(name, initial, limit) struct k_sem name = {initial}
#define K_MEM_SLAB_DEFINE_STATIC(name, size, count, align) static struct k_mem_slab name
#define K_THREAD_STACK_DEFINE(name, size) char name[size]
#define K_THREAD_STACK_SIZEOF(name) sizeof(name)
#define K_THREAD_DEFINE(name, size, fn, p1, p2, p3, priority, options, delay) void *name = (void *) fn
#define BUILD_ASSERT(v) ((void) sizeof(char[(v) ? 1 : -1]))
#define __ASSERT_NO_MSG(v) assert(v)
#define DEVICE_DT_GET(node) (&test_device)
#define DT_ALIAS(node) 0
#define DT_NODELABEL(node) 0
#define GPIO_DT_SPEC_GET_OR(node, property, fallback) (&(test_device))
#ifdef CONFIG_OMI_ENABLE_AAD_CONNECTED_QUIET
#define IS_ENABLED(v) (v)
#else
/* Only the connected-quiet symbol is queried by production mic.c. */
#define IS_ENABLED(v) 0
#endif
static inline int64_t k_uptime_get(void)
{
    return test_now;
}
static inline uint32_t k_uptime_get_32(void)
{
    return (uint32_t) test_now;
}
static inline void k_msleep(int64_t ms)
{
    test_now += ms;
}
static inline void k_sleep(int64_t ms)
{
    test_now += ms;
}
static inline void k_sem_give(struct k_sem *s)
{
    s->count = 1;
}
static inline void k_sem_reset(struct k_sem *s)
{
    s->count = 0;
}
int k_sem_take(struct k_sem *s, int64_t timeout);
static inline k_spinlock_key_t k_spin_lock(struct k_spinlock *s)
{
    ARG_UNUSED(s);
    return 0;
}
static inline void k_spin_unlock(struct k_spinlock *s, k_spinlock_key_t key)
{
    ARG_UNUSED(s);
    ARG_UNUSED(key);
}
static inline void k_mem_slab_free(struct k_mem_slab *s, void *buf)
{
    ARG_UNUSED(s);
    ARG_UNUSED(buf);
    ++test_freed;
}
static inline void k_thread_start(void *id)
{
    ARG_UNUSED(id);
}
static inline void k_thread_abort(void *id)
{
    ARG_UNUSED(id);
}
static inline void k_thread_name_set(void *id, const char *name)
{
    ARG_UNUSED(id);
    ARG_UNUSED(name);
}
static inline void *k_thread_create(struct k_thread *thread,
                                    void *stack,
                                    size_t size,
                                    void (*fn)(void *, void *, void *),
                                    void *p1,
                                    void *p2,
                                    void *p3,
                                    int priority,
                                    int options,
                                    int64_t delay)
{
    ARG_UNUSED(stack);
    ARG_UNUSED(size);
    ARG_UNUSED(fn);
    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);
    ARG_UNUSED(priority);
    ARG_UNUSED(options);
    ARG_UNUSED(delay);
    return thread;
}
static inline bool device_is_ready(const struct device *d)
{
    return d != NULL;
}
struct gpio_dt_spec {
    const struct device *port;
    unsigned pin;
};
struct gpio_callback {
    int unused;
};
#define GPIO_INPUT 1
#define GPIO_PULL_DOWN 2
#define GPIO_INT_EDGE_RISING 3
#define GPIO_INT_DISABLE 4
static inline bool gpio_is_ready_dt(const struct gpio_dt_spec *s)
{
    return s->port != NULL;
}
static inline int gpio_pin_configure_dt(const struct gpio_dt_spec *s, int flags)
{
    ARG_UNUSED(s);
    ARG_UNUSED(flags);
    return 0;
}
static inline int gpio_pin_interrupt_configure_dt(const struct gpio_dt_spec *s, int flags)
{
    ARG_UNUSED(s);
    ARG_UNUSED(flags);
    return 0;
}
static inline int gpio_pin_get_dt(const struct gpio_dt_spec *s)
{
    ARG_UNUSED(s);
    return test_wake_level;
}
static inline void gpio_init_callback(struct gpio_callback *cb,
                                      void (*fn)(const struct device *, struct gpio_callback *, uint32_t),
                                      unsigned pins)
{
    ARG_UNUSED(cb);
    ARG_UNUSED(fn);
    ARG_UNUSED(pins);
}
static inline int gpio_add_callback(const struct device *d, struct gpio_callback *cb)
{
    ARG_UNUSED(d);
    ARG_UNUSED(cb);
    return 0;
}
#define NRF_PDM0_S 0
static inline void nrf_pdm_disable(int p)
{
    ARG_UNUSED(p);
}
static inline void nrf_pdm_gain_set(int p, int l, int r)
{
    ARG_UNUSED(p);
    ARG_UNUSED(l);
    ARG_UNUSED(r);
}
struct pcm_stream_cfg {
    int pcm_width;
    struct k_mem_slab *mem_slab;
    unsigned pcm_rate;
    size_t block_size;
};
struct dmic_cfg {
    struct {
        int min_pdm_clk_freq, max_pdm_clk_freq, min_pdm_clk_dc, max_pdm_clk_dc;
    } io;
    struct pcm_stream_cfg *streams;
    struct {
        int req_num_streams, req_num_chan, req_chan_map_lo;
    } channel;
};
#define PDM_CHAN_LEFT 0
#define PDM_CHAN_RIGHT 1
#define DMIC_TRIGGER_START 1
#define DMIC_TRIGGER_STOP 2
static inline int dmic_build_channel_map(int stream, int chan, int side)
{
    return stream + chan + side;
}
static inline int dmic_configure(const struct device *d, struct dmic_cfg *cfg)
{
    ARG_UNUSED(d);
    ARG_UNUSED(cfg);
    return 0;
}
static inline int dmic_trigger(const struct device *d, int trigger)
{
    ARG_UNUSED(d);
    if (trigger == DMIC_TRIGGER_START)
        ++test_starts;
    else
        ++test_stops;
    return 0;
}
int dmic_read(const struct device *d, int stream, void **buf, uint32_t *size, int timeout);
static inline void test_log(const char *fmt, ...)
{
    ARG_UNUSED(fmt);
}
#define LOG_MODULE_REGISTER(...)
#define LOG_ERR(...) test_log(__VA_ARGS__)
#define LOG_INF(...) test_log(__VA_ARGS__)
#define LOG_WRN(...) test_log(__VA_ARGS__)
#define LOG_DBG(...) test_log(__VA_ARGS__)
#endif
