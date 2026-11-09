#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>

#include "diagnostics.h"
int64_t test_uptime;
#ifndef CONFIG_BT_EATT
#define CONFIG_BT_EATT 0
#endif
#define CONFIG_BT_MAX_CONN 2
#define BUILD_ASSERT(c, m) _Static_assert(c, m)
#define IS_ENABLED(c) (c)
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define BT_GATT_ERR(e) (-(e))
#define BT_ATT_ERR_INVALID_OFFSET 7
#define BT_ATT_ERR_UNLIKELY 14
struct bt_conn {
    uint8_t index;
};
struct bt_gatt_attr {
    int unused;
};
static uint8_t bt_conn_index(struct bt_conn *c)
{
    return c->index;
}
struct k_spinlock {
    _Atomic unsigned busy;
};
typedef unsigned k_spinlock_key_t;
static k_spinlock_key_t k_spin_lock(struct k_spinlock *l)
{
    while (atomic_exchange_explicit(&l->busy, 1, memory_order_acquire))
        sched_yield();
    return 0;
}
static void k_spin_unlock(struct k_spinlock *l, k_spinlock_key_t key)
{
    (void) key;
    atomic_store_explicit(&l->busy, 0, memory_order_release);
}
/* Zephyr copy semantics shim, not the production ATT implementation. */
static ssize_t bt_gatt_attr_read(struct bt_conn *conn,
                                 const struct bt_gatt_attr *attr,
                                 void *buf,
                                 uint16_t len,
                                 uint16_t offset,
                                 const void *value,
                                 uint16_t size)
{
    (void) conn;
    (void) attr;
    if (offset > size)
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    if (len > size - offset)
        len = size - offset;
    memcpy(buf, (const uint8_t *) value + offset, len);
    return len;
}
static void recovery_reset_read_cache(struct bt_conn *conn)
{
    (void) conn;
}
#include "diagnostics_gatt_block.inc"
static uint32_t rd(const uint8_t *p)
{
    return (uint32_t) p[0] | (uint32_t) p[1] << 8 | (uint32_t) p[2] << 16 | (uint32_t) p[3] << 24;
}
static void *stress(void *arg)
{
    struct bt_conn *c = arg;
    uint8_t b[25];
    for (unsigned i = 0; i < 10000; i++) {
        assert(diagnostics_read_handler(c, 0, b, 22, 0) == 22);
        omi_diagnostics_inc_storage_error();
        assert(diagnostics_read_handler(c, 0, b + 22, 3, 22) == 3);
        if (i % 7 == 0)
            diagnostics_reset_read_cache(c);
    }
    return 0;
}
static void *reset_stress(void *arg)
{
    for (unsigned i = 0; i < 10000; i++)
        diagnostics_reset_read_cache(arg);
    return 0;
}
int main(void)
{
    struct bt_conn a = {0}, b = {1}, invalid = {2};
    uint8_t av[25], bv[25], v[25];
    for (unsigned i = 0; i < 255; i++)
        omi_diagnostics_inc_storage_error();
    assert(diagnostics_read_handler(&a, 0, av, 22, 0) == 22);
    omi_diagnostics_inc_storage_error();
    assert(diagnostics_read_handler(&b, 0, bv, 22, 0) == 22);
    omi_diagnostics_inc_storage_error();
    assert(diagnostics_read_handler(&a, 0, av + 22, 3, 22) == 3);
    assert(diagnostics_read_handler(&b, 0, bv + 22, 3, 22) == 3);
    assert(rd(av + 21) == 255 && rd(bv + 21) == 256);
    /* Invalid offsets cannot invalidate the pinned snapshot. */
    assert(diagnostics_read_handler(&a, 0, v, 25, 26) == -7);
    assert(diagnostics_read_handler(&a, 0, av + 21, 4, 21) == 4 && rd(av + 21) == 255);
    assert(diagnostics_read_handler(&a, 0, v, 25, 25) == 0);
    assert(diagnostics_read_handler(&a, 0, v, 25, 0) == 25 && rd(v + 21) == 257);
    /* Simulate disconnect then same-index reconnect; no pointer is retained. */
    diagnostics_reset_read_cache(&a);
    struct bt_conn replacement = {0};
    omi_diagnostics_inc_storage_error();
    assert(diagnostics_read_handler(&replacement, 0, v + 21, 4, 21) == 4 && rd(v + 21) == 258);
    omi_diagnostics_inc_storage_error();
    assert(diagnostics_read_handler(&replacement, 0, v + 21, 4, 21) == 4 && rd(v + 21) == 258);
    assert(diagnostics_read_handler(&replacement, 0, v, 25, 0) == 25 && rd(v + 21) == 259);
    assert(diagnostics_read_handler(0, 0, v, 25, 0) == -14);
    assert(diagnostics_read_handler(&invalid, 0, v, 25, 0) == -14);
    diagnostics_reset_read_cache(0);
    diagnostics_reset_read_cache(&invalid);
    pthread_t t1, t2, t3;
    assert(!pthread_create(&t1, 0, stress, &a));
    assert(!pthread_create(&t2, 0, stress, &b));
    assert(!pthread_create(&t3, 0, reset_stress, &a));
    assert(!pthread_join(t1, 0));
    assert(!pthread_join(t2, 0));
    assert(!pthread_join(t3, 0));
    puts("PASS coherence, refresh, interleaved clients, direct offsets, invalid offsets, lifecycle slot reuse, "
         "concurrent cache read/reset stress");
    return 0;
}
