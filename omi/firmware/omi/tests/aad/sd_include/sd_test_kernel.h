#ifndef SD_TEST_KERNEL_H
#define SD_TEST_KERNEL_H
#include <stdio.h>
#include <string.h>
#include <test_kernel.h>
#define snprintk snprintf
#undef BUILD_ASSERT
#define BUILD_ASSERT(v, ...) typedef char sd_layout_assert[(v) ? 1 : -1]
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define CONFIG_SDMMC_VOLUME_NAME "host"
#define CONFIG_LOG_DEFAULT_LEVEL 3
#define GPIO_OUTPUT 5
#define GPIO_DISCONNECTED 6
#define PM_DEVICE_ACTION_RESUME 1
#define PM_DEVICE_ACTION_SUSPEND 2
#define DISK_IOCTL_CTRL_INIT 1
#define DISK_IOCTL_CTRL_DEINIT 2
#define DISK_IOCTL_CTRL_SYNC 3
#define DISK_IOCTL_GET_SECTOR_COUNT 4
#define DISK_IOCTL_GET_SECTOR_SIZE 5

typedef void *k_tid_t;
typedef void (*k_thread_entry_t)(void *, void *, void *);
struct k_msgq {
    size_t size;
};
#define K_MSGQ_DEFINE(name, size, count, align) struct k_msgq name = {size}
int k_msgq_put(struct k_msgq *q, const void *data, k_timeout_t timeout);
static inline int k_msgq_get(struct k_msgq *q, void *data, k_timeout_t timeout)
{
    (void) q;
    (void) data;
    (void) timeout;
    return -EAGAIN;
}
static inline unsigned k_msgq_num_used_get(struct k_msgq *q)
{
    (void) q;
    return 0;
}
static inline void k_sem_init(struct k_sem *s, unsigned initial, unsigned limit)
{
    (void) limit;
    s->count = initial;
}
static inline int gpio_pin_set_dt(const struct gpio_dt_spec *s, int value)
{
    (void) s;
    (void) value;
    return 0;
}
static inline int gpio_pin_set_raw(const struct device *d, unsigned pin, int value)
{
    (void) d;
    (void) pin;
    (void) value;
    return 0;
}
static inline int gpio_pin_configure(const struct device *d, unsigned pin, int flags)
{
    (void) d;
    (void) pin;
    (void) flags;
    return 0;
}
static inline int pm_device_action_run(const struct device *d, int action)
{
    (void) d;
    (void) action;
    return 0;
}
int disk_access_read(const char *name, void *buf, uint32_t sector, uint32_t count);
int disk_access_write(const char *name, const void *buf, uint32_t sector, uint32_t count);
int disk_access_ioctl(const char *name, unsigned command, void *out);
static inline void sys_put_be32(uint32_t v, uint8_t *p)
{
    p[0] = v >> 24;
    p[1] = v >> 16;
    p[2] = v >> 8;
    p[3] = v;
}
static inline uint32_t sys_get_be32(const uint8_t *p)
{
    return ((uint32_t) p[0] << 24) | ((uint32_t) p[1] << 16) | ((uint32_t) p[2] << 8) | p[3];
}
#endif
