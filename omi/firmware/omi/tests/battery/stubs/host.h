#pragma once
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define CONFIG_LOG_DEFAULT_LEVEL 0
#define LOG_MODULE_REGISTER(...)
#define LOG_INF(...)
#define LOG_WRN(...)
#define LOG_ERR(...)
#define LOG_PRINTK(...)
#define BIT(n) (1U << (n))
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define K_FOREVER 0
#define K_MSEC(n) (n)
#define K_MUTEX_DEFINE(n) int n
struct k_spinlock {
    int held;
};
typedef int k_spinlock_key_t;
static inline int k_spin_lock(struct k_spinlock *l)
{
    assert(!l->held);
    l->held = 1;
    return 0;
}
static inline void k_spin_unlock(struct k_spinlock *l, int key)
{
    (void) key;
    assert(l->held);
    l->held = 0;
}
static inline void k_mutex_lock(int *m, int timeout)
{
    (void) timeout;
    assert(!*m);
    *m = 1;
}
static inline void k_mutex_unlock(int *m)
{
    assert(*m);
    *m = 0;
}
static inline void k_msleep(int n)
{
    (void) n;
}
static inline void k_busy_wait(int n)
{
    (void) n;
}
struct device {
    const char *name;
};
static const struct device fake_device = {"host"};
#define DEVICE_DT_GET(n) (&fake_device)
#define DT_NODELABEL(n) n
// clang-format off: local and CI versions disagree on a brace in a macro body.
#define GPIO_DT_SPEC_GET_OR(...) {.port = &fake_device, .pin = 0}
// clang-format on
struct gpio_dt_spec {
    const struct device *port;
    int pin;
};
struct gpio_callback {
    int unused;
};
#define GPIO_INPUT 1
#define GPIO_OUTPUT 2
#define GPIO_PULL_UP 4
#define GPIO_INT_EDGE_BOTH 8
#define NRF_GPIO_DRIVE_S0H1 0
extern int test_charge_pin;
static inline int device_is_ready(const struct device *d)
{
    (void) d;
    return 1;
}
static inline int gpio_pin_configure_dt(const struct gpio_dt_spec *s, int f)
{
    (void) s;
    (void) f;
    return 0;
}
static inline int gpio_pin_set(const struct device *d, int pin, int v)
{
    (void) d;
    (void) pin;
    (void) v;
    return 0;
}
static inline int gpio_pin_get(const struct device *d, int pin)
{
    (void) d;
    (void) pin;
    return test_charge_pin;
}
static inline int gpio_pin_interrupt_configure_dt(const struct gpio_dt_spec *s, int f)
{
    (void) s;
    (void) f;
    return 0;
}
static inline void gpio_init_callback(struct gpio_callback *c,
                                      void (*cb)(const struct device *, struct gpio_callback *, uint32_t),
                                      uint32_t pins)
{
    (void) c;
    (void) cb;
    (void) pins;
}
static inline int gpio_add_callback(const struct device *d, struct gpio_callback *c)
{
    (void) d;
    (void) c;
    return 0;
}
#define ADC_GAIN_1_3 0
#define ADC_REF_INTERNAL 0
#define ADC_ACQ_TIME(a, b) 0
struct adc_channel_cfg {
    int gain, reference, acquisition_time, channel_id;
};
struct adc_sequence_options {
    int extra_samplings, interval_us;
    void *callback, *user_data;
};
struct adc_sequence {
    const struct adc_sequence_options *options;
    int channels;
    void *buffer;
    size_t buffer_size;
    int resolution;
};
static struct {
    int TASKS_CALIBRATEOFFSET;
} fake_saadc;
#define NRF_SAADC_S (&fake_saadc)
extern int test_adc_mv, test_adc_error;
extern void (*test_adc_hook)(void);
static inline int adc_channel_setup(const struct device *d, const struct adc_channel_cfg *c)
{
    (void) d;
    (void) c;
    return 0;
}
static inline int adc_read(const struct device *d, const struct adc_sequence *s)
{
    (void) d;
    for (size_t i = 0; i < s->buffer_size / sizeof(int16_t); i++)
        ((int16_t *) s->buffer)[i] = (int16_t) test_adc_mv;
    if (test_adc_hook)
        test_adc_hook();
    return test_adc_error;
}
static inline int adc_ref_internal(const struct device *d)
{
    (void) d;
    return 600;
}
static inline int adc_raw_to_millivolts(int r, int g, int n, int32_t *v)
{
    (void) r;
    (void) g;
    (void) n;
    (void) v;
    return 0;
}
